# Déploiement Utilisateur - SIVE (Scrap Ingest Vectorize Extends)

Ce guide est pensé pour un utilisateur qui veut:

- installer l outil via pip
- le brancher comme serveur MCP dans son projet
- ingester une documentation sans config complexe
- utiliser la recherche de documentation depuis son assistant

## Positionnement du service

Ce service est adapté à l'indexation de données peu évolutives
(documentations, référentiels, contenus stables).

Il n'est pas destiné à l'indexation de données qui évoluent régulièrement
ou en continu. Pour ce type de données, il faut privilégier un pipeline
de synchronisation plus fréquente et une architecture de traitement dédiée.

## 1) Prérequis

- Python 3.11+
- pip
- GitHub Copilot CLI, Claude Code, Codex ou OpenCode v2

## 2) Installation (uv recommandé)

### Option A - installation globale avec uv (recommandé)

```bash
uv tool install sive
sive --help
```

Pour afficher le dossier d'installation des exécutables:

```bash
uv tool dir
```

Si la commande n'est pas visible, ajoutez ce dossier a votre `PATH`.

### Option B - installation projet avec uv

```bash
uv venv
uv pip install -e .
```

### Option C - installation via pip (fallback)

Installez le package dans votre environnement projet (venv recommandé):

```bash
pip install sive
```

Pour installer la commande dans `~/.local/bin` (Linux/macOS):

```bash
python -m pip install --user sive
export PATH="$HOME/.local/bin:$PATH"
sive --help
```

Important:

- Le package ne peut pas forcer le répertoire d'installation des exécutables.
- C'est `pip` (et son mode `--user`/venv/systeme) qui décide la destination.
- Si `sive` n'est pas trouvé, vérifiez que le dossier cible est dans votre `PATH`.

Verifiez l'installation:

```bash
python -m sive --help
sive --help
```

L'installation avec pip ou `uv tool install` expose une seule commande: `sive`.
Le dépôt officiel est https://github.com/vjournet-dev/SIVE.

### Installer la skill SIVE et le MCP

Après installation, exécutez une fois:

```bash
sive install --target all
```

Seules les cibles `github`, `claude`, `codex`, `opencode` sont supportées.

| Cible | Skill personnelle | Configuration MCP native |
| --- | --- | --- |
| `github` (GitHub Copilot CLI) | `~/.copilot/skills/sive/SKILL.md` | `~/.copilot/mcp-config.json` |
| `claude` (Claude Code) | `~/.claude/skills/sive/SKILL.md` | `~/.claude.json` |
| `codex` | `~/.agents/skills/sive/SKILL.md` | `~/.codex/config.toml` |
| `opencode` (v2) | `~/.config/opencode/skills/sive/SKILL.md` | `~/.config/opencode/opencode.json(c)` |

La skill est un `SKILL.md` avec frontmatter `name` et `description`, chargé par
le client quand de la documentation est pertinente. Aucun prompt système n'est
généré. Les autres serveurs et réglages MCP existants sont conservés; les fichiers
invalides sont signalés sans écrasement. Les commentaires TOML sont conservés,
mais les commentaires JSONC sont retirés lors de la réécriture.
Les anciens fichiers de prompts ne sont pas supprimés automatiquement:
retirez-les des profils clients si vous les aviez activés.

Vous pouvez forcer un dossier de sortie explicite:

```bash
sive install --target codex --output-dir ./out/skills
```

Important: uv/pip ne peuvent pas executer un hook post-install universel pour configurer les clients LLM. Cette commande doit être lancee manuellement une fois après installation.

L'export contient `sive/SKILL.md` et les snippets natifs de la cible
(`codex.mcp.toml` dans cet exemple). Avec `all`, il ajoute `github.mcp.json`,
`claude.mcp.json` et `opencode.mcp.json`. L'export n'active pas les clients.

Par défaut, le MCP lance `sive serve`, ou le Python courant avec `-m sive serve`.
Le `cwd` est le dossier de l'exécutable sauf pour Claude Code, qui ne supporte
pas ce champ dans sa configuration stdio.

Vous pouvez imposer les valeurs de config MCP:

```bash
sive install --target all --python-executable "C:/path/to/python.exe" --mcp-cwd "C:/path/to/project"
```

Rechargez les skills ou redémarrez votre client. La skill demande de découvrir
les sources avec `list_documentation_sites_in_database`, puis de chercher chaque
concept avec `search_documentation` avant de répondre ou coder, en citant les
sources. Si une documentation pertinente manque, elle propose de l'ingérer avec
SIVE après confirmation du périmètre, puis de rechercher à nouveau.
Si le MCP est indisponible, le CLI peut ingérer les sources confirmées; la
recherche nécessite un client connecté à `sive serve` (pas de commande CLI
autonome de recherche). Le chargement reste soumis aux permissions du client.

## 3) Lancer le serveur MCP localement

```bash
python -m sive serve
```

Le serveur expose les tools MCP suivants:

- list_documentation_sites_in_database(include_active=True)
- list_indexed_doc_sites()
- search_documentation(query, top_k=5, site_id=None, site_ids=None, topic=None)
- suggest_documentation_urls(topic, max_results=5)
- ingest(url, incremental=True, max_pages=1200, delay=0.2, additional_urls=None, allowed_url_prefixes=None, site_id=None, site_name=None)
- update_site_differential(site_id, max_pages=1200, delay=0.2)
- ingest_and_register_topic(topic, url, incremental=True, max_pages=1200, delay=0.2)
- get_site_sync_status(site_id)
- list_site_sync_status(sort_by="staleness", descending=True, limit=100)
- ingest_status(job_id)
- wait_for_ingest_completion(job_id, poll_interval_seconds=2.0, timeout_seconds=600.0)
- delete_documentation_site(site_id, delete_raw_files=True)

## 4) Workflow recommandé (nouveau)

### Cas A - l utilisateur utilisé les commandes /sive

Le client peut exposer les commandes suivantes:

- /sive add <url | nom>
- /sive list
- /sive remove <doc_id>
- /sive help

Comportement recommandé:

- /sive add <url | nom> -> appeler ingest(url=<argument>)
- si ingest retourne plusieurs suggestions (ou needs_confirmation), demander confirmation utilisateur avant de relancer ingest(url=<url_choisie>)
- /sive list -> appeler list_documentation_sites_in_database(include_active=True)
- /sive remove <doc_id> -> appeler delete_documentation_site(site_id=<doc_id>, delete_raw_files=True)

1. Appeler ingest(url=<argument utilisateur ou URL confirmée>).
2. Suivre le job avec une des deux options:
  - polling: ingest_status(job_id) pour afficher la progression (progress_percent, phase, visited_urls, pages_kept, queued_urls)
  - attente bloquante: wait_for_ingest_completion(job_id) pour être notifié quand le job finit
3. Rechercher ensuite avec search_documentation(..., topic=...).

Les résultats de recherche MCP incluent maintenant aussi:

- `Source Kind` pour identifier le type de source (`csv`, `xlsx`, `json`, `pdf`, `docx`, etc.)
- `Section Type` pour qualifier le chunk (`summary`, `columns`, `row`, `page`, `section`)
- `Semantic Relevance` pour la similarité vectorielle
- `Rank Score` pour le classement combine applique par le domaine

Pour comparer plusieurs documentations, utilisez `site_ids=[...]`. Une route de topic peut aussi contenir plusieurs sites: le serveur interroge chaque source, fusionne les candidats et diversifie le résultat final. `site_id` reste disponible pour les clients existants.

Pour les sources tabulaires, cela aide a séparer les questions de structure (colonnes, nombre de lignes, feuille) des questions sur une ligne spécifique.

### Cas B - l utilisateur ne fournit pas d URL

1. Appeler suggest_documentation_urls(topic).
2. Proposer les suggestions a l utilisateur.
3. Une fois l URL choisie, appeler ingest(url).
4. Suivre le job via ingest_status(job_id) ou wait_for_ingest_completion(job_id).

### Cas C - ingestion de fichier local ou distant direct

Le tool ingest accepte aussi:

- un chemin local vers un fichier: .csv, .html, .htm, .md, .markdown, .docx, .json, .pdf, .xlsx
- un chemin local vers un dossier contenant ces formats
- une URL distante directe de fichier: .csv, .md, .markdown, .docx, .json, .pdf, .xlsx

### Cas D - plusieurs branches web dans une documentation

Pour crawler plusieurs branches du même host sous un seul `site_id`, appeler `ingest` avec une URL primaire, `additional_urls` et une allowlist explicite `allowed_url_prefixes`. Les préfixes peuvent être des chemins ou des URL absolues du même host. Le serveur rejette les hosts mélangés et toute URL de départ hors allowlist.

Exemple Open XML:

```text
ingest(
  url="https://learn.microsoft.com/en-us/office/open-xml/",
  additional_urls=["https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml"],
  allowed_url_prefixes=[
    "https://learn.microsoft.com/en-us/office/open-xml/",
    "https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml"
  ],
  site_id="openxml",
  site_name="Open XML"
)
```

Pour une source locale, le `site_id`/`doc_id` est dérivé automatiquement du chemin local:

- prefixe lisible base sur le nom du fichier ou du dossier
- suffixe hash court dérivé du chemin resolu
- objectif: éviter les collisions si deux dossiers distincts portent le même nom final

Exemples:

- /sive add C:/docs/guide.pdf
- /sive add C:/docs/my-folder
- /sive add https://buildmedia.readthedocs.org/media/pdf/pymupdf/latest/pymupdf.pdf

## 5) Garde-fous intégrés (important)

- Les suggestions web visent des pages de depart de documentation (pas des roots generiques quand une meilleure page est detectable).
- ingest valide l URL avant mise en file:
  - si la cible retourne HTTP 404, le serveur repond avec un payload explicite
  - le message demande une URL de premiere page de doc (exemple: .../docs/intro)
- ingest_and_register_topic reutilise ingest:
  - si URL invalide (404), la route topic -> site nest pas enregistree
  - le payload inclut route_registered=false

## 6) Integrer le MCP dans votre projet

### 6.1 Mapping explicite des commandes client `/sive`

Point cle: le slash command est gere par le client. Le serveur expose le tool MCP `ingest` pour demarrer l'ingestion.

Important: pip ne peut pas enregistrer `/sive` universellement. `sive install`
déploie la skill pour les quatre clients supportés; son invocation explicite
dépend du client. Le mapping des sous-commandes est contenu dans la skill.

Vous devez configurer le client pour transformer:

- `/sive add <url | nom>` -> `ingest(url="<argument>")`
- `/sive list` -> `list_documentation_sites_in_database(include_active=True)`
- `/sive remove <doc_id>` -> `delete_documentation_site(site_id="<doc_id>", delete_raw_files=True)`
- `/sive help` -> afficher une aide sans mutation MCP

Comportement recommandé côté client:

1. Appeler `ingest(url=...)`.
2. Recuperer le `job_id` et suivre avec `ingest_status` ou `wait_for_ingest_completion`.

### 6.2 Test rapide des commandes `/sive`

Une fois la regle client en place, validez ces cas:

1. Add URL directe:
  - `/sive add https://playwright.dev/docs/intro`
  - attendu: retour avec `job_id`
2. Add URL invalide:
  - `/sive add https://playwright.dev/docs`
  - attendu: `invalid_start_url` avec message explicite et suggestion potentielle
3. List:
  - `/sive list`
  - attendu: liste des sources en base (actives + indexees)
4. Remove:
  - `/sive remove <doc_id>`
  - attendu: suppression source et fichiers bruts associés
  - note: pour une source locale, récupérer d'abord le `doc_id` exact via `/sive list` (ex: `local-my-folder-1a2b3c4d`)
5. Suivi:
  - appeler `ingest_status(job_id)` puis eventuellement `wait_for_ingest_completion(job_id)`
  - attendu: progression puis statut final

Exemple de configuration utilisateur Claude Code (`~/.claude.json`):

```json
{
  "mcpServers": {
    "sive": {
      "type": "stdio",
      "command": "C:/path/to/your/project/.venv/Scripts/python.exe",
      "args": ["-m", "sive", "serve"]
    }
  }
}
```

N'ajoutez pas de prompt système à la configuration MCP: le workflow est dans
la skill. Utilisez `sive install` pour obtenir le format natif du client:
GitHub utilise `mcpServers` avec `type: local` et `tools: ["*"]`; Codex utilise
`[mcp_servers.sive]` en TOML; OpenCode v2 utilise `mcp.servers.sive` avec un
tableau `command`. Les références officielles sont dans le [README](README.md).

Utilisez un exécutable absolu stable (Python du venv ou `sive` installé).

## 7) Auth Hugging Face (optionnel)

Si votre environnement exige un token HF pour le modèle d embedding:

```bash
# Windows PowerShell
$env:HF_TOKEN = "hf_xxx"

# Linux/macOS
export HF_TOKEN="hf_xxx"
```

Variables reconnues:

- HUGGINGFACE_HUB_TOKEN
- HF_TOKEN
- HUGGINGFACE_TOKEN

## 8) Verification rapide

1. Demarrer le serveur.
2. Dans le client MCP, appeler list_indexed_doc_sites().
3. Si vide, lancer ingest_and_register_topic(topic, url).
4. Poller ingest_status(job_id).
  - ou appeler wait_for_ingest_completion(job_id) pour un retour final direct
5. Rejouer search_documentation(query, topic=...).

## 9) Depannage

### La commande ne fonctionne pas

```bash
pip install --upgrade sive
python -m sive --help
```

### Le MCP ne voit pas le module

Cause fréquente: le client utilisé un autre Python que celui du venv projet.

Solution: configurez command avec le chemin absolu vers .venv/Scripts/python.exe (Windows) ou .venv/bin/python (Linux/macOS).

### Ingestion refusee avec invalid_start_url

Votre URL ne pointe pas vers une page valide de documentation (404).

Solution: utilisez une URL de premiere page de doc (exemple: /docs/intro), ou passez par suggest_documentation_urls(topic).

## 10) Liens utiles

- Guide développeur: DEVELOPMENT.md
- Vue d ensemble: README.md
