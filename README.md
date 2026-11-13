# SIVE (Scrap Ingest Vectorize Extends)

Agent Python pour:

- Scraper une ou plusieurs documentations à partir d'URLs paramétrables
- La stocker dans une base vectorielle locale (Chroma)
- Exposer une recherche documentaire multi-site via un serveur MCP (transport `stdio`)

## Positionnement du projet

Ce projet a pour vocation d'indexer des documentations et contenus peu évolutifs.

Il n'est pas conçu pour indexer des données qui évoluent régulièrement (flux fréquents,
contenus opérationnels mis à jour en continu, données quasi temps réel).

Pour des données fortement évolutives, prévoir une architecture orientée synchro fréquente
et pipeline de données dédié, plutôt que cet usage MCP documentaire.

## Prérequis

- Python 3.11+
- Accès réseau aux documentations à indexer

## Auth Hugging Face (optionnel)

Si le modèle d'embedding doit être téléchargé depuis Hugging Face Hub avec authentification,
vous pouvez fournir un token via variable d'environnement.

Variables supportées (ordre de priorité):

- `HUGGINGFACE_HUB_TOKEN`
- `HF_TOKEN`
- `HUGGINGFACE_TOKEN`

Le serveur MCP et les commandes d'indexation réutilisent automatiquement ce token si présent.

Exemples:

```bash
# Windows PowerShell
$env:HF_TOKEN = "hf_xxx"

# Linux/macOS
export HF_TOKEN="hf_xxx"
```

## Installation (uv recommandé)

### Installation avec uv (recommandé)

```bash
# Installer le package comme outil global
uv tool install sive

# Vérifier les commandes installées
sive --help
```

Avec `uv tool install`, les exécutables sont installés dans le répertoire d'outils uv
(souvent sous `~/.local/bin` sur Linux/macOS).

Pour connaitre le répertoire exact:

```bash
uv tool dir
```

Si besoin, ajoutez ce répertoire a votre `PATH`.

### Installation projet (développement) avec uv

```bash
# Cloner le repo
git clone https://github.com/vjournet-dev/SIVE.git
cd SIVE

# Créer le venv et installer le projet en editable
uv venv
uv pip install -e .

# Option dev
uv pip install -e ".[dev]"
```

### Installation reproductible avec uv.lock

Pour garantir exactement le meme graphe de dependances entre dev, CI et outils uv,
utilisez le lockfile versionne:

```bash
# Depuis la racine du projet
uv sync --locked --extra dev

# Vérifier la version MCP résolue
python -c "import importlib.metadata as md; print(md.version('mcp'))"
```

Installer la CLI en mode tool avec cette version locale (sans créer de release):

```bash
uv tool uninstall sive
uv tool install "sive @ file:///C:/path/to/SIVE"

# Vérification du module MCP v2
uv tool run --from sive python -c "import importlib.util; print(bool(importlib.util.find_spec('mcp.server.mcpserver')))"
```

Notes:

- `uv sync --locked` doit échouer si `pyproject.toml` et `uv.lock` divergent (protection volontaire).
- Après modification des dépendances, exécuter `uv lock` puis `uv sync --locked`.

### Installation avec pip (fallback)

### Installation simple (depuis le repository)

```bash
# Cloner le repo
git clone https://github.com/vjournet-dev/SIVE.git
cd SIVE

# Créer et activer un venv
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Installer en mode développement
pip install -e .
```

### Installation depuis PyPI (quand publié)

```bash
pip install sive
```

### Installation utilisateur (Linux/macOS) pour exposer la commande dans `~/.local/bin`

```bash
python -m pip install --user sive
export PATH="$HOME/.local/bin:$PATH"
sive --help
```

Important:

- Le dossier d'installation des exécutables est choisi par `pip` (pas par le package).
- Pour viser `~/.local/bin`, utilisez `pip install --user`.
- Si la commande n'est pas visible, ajoutez `~/.local/bin` au `PATH` de votre shell.

Windows equivalent:

- Les exécutables sont installés dans le dossier `Scripts` de l'environnement Python (venv) ou dans `%APPDATA%\Python\PythonXY\Scripts` avec `--user`.

### Installation avec dépendances de développement

```bash
pip install -e ".[dev]"
```

### Vérifier l'installation

```bash
sive --help
```

Si la commande n'est pas reconnue, assurez-vous que le venv est activé.

Avec pip ou uv, un seul exécutable CLI est installé:

- `sive`

Le package Python s'appelle également `sive` (`python -m sive`).
Le dépôt officiel est https://github.com/vjournet-dev/SIVE.

### Installer les skills/prompts client `/sive`

Après installation (uv ou pip), exécutez une fois:

```bash
sive install --target all
```

Emplacements par défaut:

- Claude: `~/.claude/skills/sive` (`SKILL.md`, `SYSTEM_PROMPT.txt`)
- Copilot: `~/.copilot/instructions` (`sive.instructions.md`)
- GPT: `~/.sive/gpt` (`SYSTEM_PROMPT.txt`)
- Gemini: `~/.sive/gemini` (`SYSTEM_PROMPT.txt`)
- Microsoft Cowork: `~/OneDrive/Documents/Cowork/skills/sive` (`SKILL.md`, `references/README-COWORK.md`, `references/manifest.json`, `references/MCP_SERVER.json`, `references/color.png`, `references/outline.png`)

Override possible vers un dossier explicite:

```bash
sive install --target copilot --output-dir ./out/prompts
```

Important: ni uv ni pip ne permettent d'executer automatiquement un hook post-install portable pour configurer tous les clients LLM. Lancez donc `sive install` une fois après installation.

La commande `sive install` installé maintenant aussi des fichiers de configuration MCP client (avec le Python/cwd détectés automatiquement):

- Claude: `MCP_SERVER.json`
- Copilot: `sive.mcp.json`
- GPT/Gemini: `MCP_SERVER.json`

Pour Microsoft Cowork, l'installation écrit la skill dans le dossier OneDrive recommandé par la documentation Cowork (`~/OneDrive/Documents/Cowork/skills/sive/`). Elle copie aussi des ressources de référence (`README-COWORK.md`, `manifest.json`, `MCP_SERVER.json`) ainsi que `color.png` et `outline.png`.

Important pour Cowork: le fichier `MCP_SERVER.json` copié est un artefact de configuration locale (command/cwd) utile comme référence, mais Copilot Cowork n'exécute pas un serveur MCP local `stdio` directement. Pour un appel d'outils effectif dans Cowork, il faut un connecteur MCP distant en HTTPS déclaré dans le manifeste de plugin (`agentConnectors.remoteMcpServer`).

Par défaut, la config MCP générée utilisé l'exécutable installé `sive` (par exemple dans `~/.local/bin` ou le dossier `Scripts`) avec `serve` comme argument. Le `cwd` par défaut est le dossier de cet exécutable.

Vous pouvez surcharger les valeurs ecrites dans la config MCP:

```bash
sive install --target all --python-exécutable "C:/path/to/python.exe" --mcp-cwd "C:/path/to/project"
```

## Utilisation

## Nouveautés récentes

Les changements suivants sont actifs dans le serveur MCP:

- Nouveau tool `list_documentation_sites_in_database(include_active=True)` pour lister toutes les sources enregistrees (indexees + eventuellement actives).
- Nouveau tool `ingest(...)` pour lancer une ingestion asynchrone depuis le client MCP.
- Nouveau tool `update_site_differential(site_id, ...)` pour mettre à jour de manière differentielle un site deja indexe.
- Nouveau tool `get_site_sync_status(site_id)` pour récupérer les dates/heures de dernier scraping et indexation d'un site.
- Nouveau tool `list_site_sync_status(sort_by, descending, limit)` pour lister tous les sites et prioriser les updates par anciennete.
- Nouveau tool `ingest_status(job_id)` pour suivre un job (`queued`, `running`, `awaiting_authentication`, `succeeded`, `failed`).
- Nouveau tool `wait_for_ingest_completion(job_id, poll_interval_seconds=2.0, timeout_seconds=600.0)` pour attendre la fin d'un job sans gerer un polling manuel côté client.
- Nouveau tool `authenticate_ingest_job(job_id, timeout_seconds=300.0)` pour reprendre un job bloque sur une authentification interactive.
- Nouveau tool `set_ingest_auth_session(job_id, cookies, headers)` pour reprendre un job bloque avec une session deja capturee.
- Nouveau tool `set_ingest_auth_config(job_id, auth_config, timeout_seconds=300.0)` pour reprendre un job bloque avec une strategie `form`, `cookie`, `basic` ou `oauth`.
- Nouveau tool `suggest_documentation_urls(topic, max_results=5)` pour proposer des URLs de doc depuis le web quand l'utilisateur n'en fournit pas.
- Nouveau tool `ingest_and_register_topic(topic, url, ...)` pour enregistrer un sujet et lancer l'ingestion en une seule étape.
- Persistance des jobs dans `data/raw/ingest_jobs.json`.
- Persistance des routes sujet -> doc dans `data/raw/topic_routes.json`.
- Persistance du statut de synchro par site dans `data/raw/site_sync_state.json`.
- Au redémarrage du serveur, les jobs interrompus (`queued`/`running`) sont marques `failed` avec une erreur explicite de restart.
- `list_indexed_doc_sites` masque temporairement les sites en cours d'ingestion.
- `search_documentation` reste disponible pendant ingestion.
- `search_documentation` avec un `site_id` actif retourne un message d'attente pour ce site.
- `search_documentation` applique automatiquement une route sujet -> site quand un sujet enregistre est detecte dans la requete.
- Les jobs d'ingestion lances via MCP n'ecrivent plus de progression crawl sur stdout (pour éviter le bruit sur le transport JSON-RPC).
- L'ingestion accepte aussi des sources locales (fichier/dossier) pour: `.csv`, `.html`, `.htm`, `.md`, `.markdown`, `.docx`, `.json`, `.pdf`, `.xlsx`.
- Les URLs distantes directes vers des fichiers sont prises en charge pour: `.csv`, `.md`, `.markdown`, `.docx`, `.json`, `.pdf`, `.xlsx`.
- Si un site est bloque par anti-bot et qu'aucune page n'est extraite, le job echoue avec une erreur explicite.
- Si un site protege demande une connexion, le job passe en `awaiting_authentication` avec `needs_authentication=true` jusqu'a reprise par un tool d'authentification.
- Pour une URL de fichier distant direct qui retourne HTTP 401/403 (ex: PDF hosteddocs), preferer l'ingestion depuis l'URL du site ou de la bibliotheque de documents.

### 1) Ingestion complete (scrape + index)

```bash
python -m sive ingest --reset
```

Pour un site unique paramétrable:

```bash
python -m sive ingest --site-id haystack --site-name "Haystack" --start-url "https://docs.haystack.deepset.ai/docs/intro" --allowed-host docs.haystack.deepset.ai --allowed-path-prefix /docs/ --incremental
```

Pour regrouper plusieurs branches du même host dans une seule documentation, répétez les options additionnelles. Chaque URL de départ doit correspondre à l'un des préfixes autorises:

```bash
python -m sive ingest --site-id openxml --site-name "Open XML" --allowed-host learn.microsoft.com --start-url "https://learn.microsoft.com/en-us/office/open-xml/" --additional-start-url "https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml" --allowed-path-prefix "/en-us/office/open-xml/" --additional-allowed-path-prefix "/en-us/dotnet/api/documentformat.openxml" --incremental
```

Mode incremental:

```bash
python -m sive ingest --incremental
```

Ce mode recrawl la documentation, compare le hash de contenu de chaque page avec l'etat precedent, puis:

- reindexe uniquement les pages modifiees
- supprime du vector store les pages disparues
- ignore les pages inchangees

Options utiles:

- `--max-pages 1500`
- `--delay 0.3`
- `--chunk-size 1200 --chunk-overlap 200`
- `--incremental`

Les données sont ecrites dans:

- `data/raw/<site_id>.jsonl`
- `data/raw/<site_id>.state.json`
- `data/chroma/`

## Chunking semantique

Le decoupage est base sur les sections de la documentation:

- extraction des sections à partir des titres `h1` a `h6`
- prefixage de chaque chunk par le titre de page et le titre de section
- sous-decoupage par taille uniquement à l'interieur d'une section

Ce decoupage ameliore la pertinence pour les requetes ciblees sur un composant, une étape de pipeline ou une option de configuration.

### 2) Lancer le serveur MCP

```bash
python -m sive serve
```

Tool expose:

- `list_documentation_sites_in_database(include_active: bool = True)`
- `list_indexed_doc_sites()`
- `search_documentation(query: str, top_k: int = 5, site_id: str | None = None, site_ids: list[str] | None = None, topic: str | None = None)`
- `ingest(url: str, incremental: bool = True, max_pages: int = 1200, delay: float = 0.2, additional_urls: list[str] | None = None, allowed_url_prefixes: list[str] | None = None, site_id: str | None = None, site_name: str | None = None)`
- `update_site_differential(site_id: str, max_pages: int = 1200, delay: float = 0.2)`
- `get_site_sync_status(site_id: str)`
- `list_site_sync_status(sort_by: str = "staleness", descending: bool = True, limit: int = 100)`
- `ingest_status(job_id: str)`
- `wait_for_ingest_completion(job_id: str, poll_interval_seconds: float = 2.0, timeout_seconds: float = 600.0)`
- `authenticate_ingest_job(job_id: str, timeout_seconds: float = 300.0)`
- `set_ingest_auth_session(job_id: str, cookies: dict[str, str] | None = None, headers: dict[str, str] | None = None)`
- `set_ingest_auth_config(job_id: str, auth_config: dict[str, object], timeout_seconds: float = 300.0)`
- `suggest_documentation_urls(topic: str, max_results: int = 5)`
- `ingest_and_register_topic(topic: str, url: str, incremental: bool = True, max_pages: int = 1200, delay: float = 0.2)`
- `delete_documentation_site(site_id: str, delete_raw_files: bool = True)`

Workflow recommandé pour une nouvelle documentation:

0. Option UX chat: l'utilisateur peut taper `/sive add <url | nom>` qui appelle le tool MCP `ingest`.
1. L'utilisateur fournit explicitement une URL de documentation officielle.
2. Si aucune URL n'est fournie, l'agent appelle `suggest_documentation_urls(topic)` puis propose les URLs trouvees à l'utilisateur.
3. Une fois l'URL validee, l'agent appelle `ingest(url=...)` (ou `ingest_and_register_topic(topic, url)` s'il veut aussi memoriser la route topic -> site).
4. L'agent choisit un mode de suivi:
  - mode polling: appeler `ingest_status(job_id)` régulièrement pour afficher une progression (`progress_percent`, `phase`, `visited_urls`, `pages_kept`, `queued_urls`)
  - mode attente bloquante: appeler `wait_for_ingest_completion(job_id)` pour recevoir directement l'etat final et declencher une notification de fin
  - si le job passe en `awaiting_authentication`, appeler `authenticate_ingest_job(job_id)` en premier, puis reprendre `wait_for_ingest_completion(job_id)`
  - si l'authentification interactive ne suffit pas, utiliser `set_ingest_auth_session(...)` ou `set_ingest_auth_config(...)` quand une session ou une configuration sécurisée est disponible hors chat
5. Pour toutes les questions suivantes sur ce sujet, l'agent appelle `search_documentation(..., topic=...)` (route sujet appliquee automatiquement).

### Recherche multi-sites et pertinence

- `site_id` conserve le filtre singulier historique; `site_ids` permet un périmètre explicite sur plusieurs sources. Les deux paramètres ne peuvent pas être combines.
- Un même topic peut être associé à plusieurs sites. Les routes v2 existantes sont migrées automatiquement vers le schéma v3 multi-sites.
- Pour un topic multi-sites, un pool de candidats est récupéré séparément par site, puis fusionne, déduplique, reranke et diversifie afin qu'une source ne masque pas les autres avant le classement.
- Sans filtre ni route, la recherche reste globale. Une mention explicite de `site_name` ou `site_id` dans la requête peut sélectionner le site correspondant; un nom absent ou peu explicite laisse la similarité sémantique décider.
- Les sites en ingestion sont ignores lorsque d'autres sites du périmètre sont disponibles. La réponse expose les sites recherches et les sites temporairement ignores.
- `Semantic Relevance` représente la similarité vectorielle. `Rank Score` est le score combine de classement (similarité, titre, section, type de source, position et nom de site); ce n'est pas une probabilité.

### Ingestion MCP multi-URL bornee

Utilisez `additional_urls` pour indexer plusieurs branches du même host sous un seul `site_id`. Sans `allowed_url_prefixes`, le chemin complet de chaque URL de départ devient son préfixe autorise. Fournissez explicitement cette allowlist pour rendre le périmètre évident et reproductible:

```text
ingest(
  url="https://learn.microsoft.com/en-us/office/open-xml/",
  additional_urls=["https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml"],
  allowed_url_prefixes=[
    "https://learn.microsoft.com/en-us/office/open-xml/",
    "https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml",
  ],
  site_id="openxml",
  site_name="Open XML",
)
```

Contraintes:

- toutes les URL de départ et tous les préfixes absolus doivent utiliser le même host
- chaque URL de départ doit appartenir à l'allowlist
- `max_pages` s'applique au job combine
- les descendants d'API separes par `.` sont acceptes, par exemple `documentformat.openxml.packaging`
- les champs singuliers historiques restent supportes pour les jobs et états existants

Le tool de recherche retourne les extraits les plus pertinents avec identite du site, type de source, type de section, section, URL source et scores de pertinence. `site_id` restreint à une source et `site_ids` à un groupe de sources.

Pour les sources tabulaires (`.csv`, `.xlsx`), les résultats exposent typiquement:

- `Source Kind: csv` ou `xlsx`
- `Section Type: summary`, `columns` ou `row`

Cela permet de distinguer rapidement:

- un chunk de synthese de table/feuille
- un chunk de schema de colonnes
- un chunk correspondant a une ligne precise

Comportement d'ingestion MCP:

- `ingest` demarre un job asynchrone à partir d'une URL de documentation, d'un chemin local ou d'une URL de fichier distant supporté, puis retourne immediatement un `job_id`
- `update_site_differential` relance une ingestion incrementale (differentielle) pour un `site_id` deja connu, sans redonner l'URL
- `list_site_sync_status` trie par `staleness` pour identifier en premier les sites les plus anciens (ou sans historique) a mettre à jour
- `site_id` est dérivé automatiquement depuis l'URL (host + prefixe de path)
- pour une source locale (fichier ou dossier), `site_id` est dérivé du nom local et d'un hash court du chemin resolu afin d'éviter les collisions entre deux chemins differents ayant le même nom final
- `ingest_status` permet de suivre les etats `queued`, `running`, `awaiting_authentication`, `succeeded`, `failed` et expose aussi une progression live (`progress_percent`, `phase`, `visited_urls`, `pages_kept`, `queued_urls`)
- `wait_for_ingest_completion` permet un mode "notification de fin" côté client/LLM (retour final, ou timeout)
- `authenticate_ingest_job`, `set_ingest_auth_session` et `set_ingest_auth_config` permettent de reprendre un job bloque sur une authentification
- les jobs sont persistants dans `data/raw/ingest_jobs.json` et recharges au démarrage du serveur
- après redémarrage, un job interrompu est marque `failed` avec une erreur de restart (pas de reprise automatique)

Comportement de routage par sujet:

## Support Matrix (PR7)

### Ingest methods

| Source type | Resolution path | Notes |
|---|---|---|
| Local path (file/folder) | local_source plugin | Direct document ingest without HTML crawl |
| Remote direct document URL | remote_document plugin | Supports auth session for protected document endpoints |
| Web documentation URL + auth session | authenticated_scraping plugin | Uses authenticated crawl behavior |
| Web documentation URL (default) | web_scrape plugin | Standard crawler flow |

### Supported document formats

| Format | Local path | Remote direct URL |
|---|---|---|
| csv | yes | yes |
| html/htm | yes | no |
| markdown/md | yes | yes |
| docx | yes | yes |
| json | yes | yes |
| pdf | yes | yes |
| xlsx | yes | yes |

### Chunking and reranking routing

| source_kind | Chunk strategy | Rerank strategy |
|---|---|---|
| markdown | markdown | narrative |
| html | generic | narrative |
| json | generic | narrative |
| csv | table | tabular |
| xlsx | table | tabular |
| docx | word | narrative |
| pdf | pdf | pdf |
| unknown | generic fallback | generic fallback |

## Release Readiness Checklist

Use this checklist before shipping a release branch/tag.

1. Validate architecture constraints from docs/AI_ARCHITECTURE.md.
2. Validate install artifacts generation with `python -m sive install --target all --output-dir <temp_dir>`.
3. Run mandatory static and test gate:
  - `python -m ruff check src tests`
  - `python -m mypy src`
  - `python -m pytest -q`
4. Run robust runtime validation: `python scripts/e2e_runtime_validate_robust.py`.
5. Confirm persisted state files are coherent after run:
  - `data/raw/ingest_jobs.json`
  - `data/raw/topic_routes.json`
  - `data/raw/site_sync_state.json`
6. Confirm MCP tool surface includes ingest, search, admin and auth-résumé tools.

- `ingest_and_register_topic` enregistre une route `topic -> site_id` et lance l'ingestion
- `search_documentation` priorise automatiquement la documentation routee pour le sujet detecte
- si l'URL est invalide (HTTP 404), `ingest_and_register_topic` ne persiste pas la route et retourne `route_registered=false`

Comportement de listing/recherche pendant ingestion:

- `list_indexed_doc_sites` masque temporairement les sites en cours de scraping/indexation
- `list_documentation_sites_in_database(include_active=True)` permet aussi de lister les sources actives
- `search_documentation` reste disponible pendant ingestion
- si `search_documentation` cible explicitement un `site_id` en cours d'ingestion, un message de temporisation est retourne pour ce site

Commandes slash recommandees côté client:

- `/sive add <url | nom>` -> `ingest(url=<argument>)`
- `/sive list` -> `list_documentation_sites_in_database(include_active=True)`
- `/sive remove <doc_id>` -> `delete_documentation_site(site_id=<doc_id>, delete_raw_files=True)`
- `/sive help` -> affiche l'aide sans mutation MCP

Note pour les sources locales:

- si vous ingerez un dossier local, le `doc_id`/`site_id` visible dans les listings prendra une forme proche de `local-docs-1a2b3c4d`
- le suffixe hash est dérivé du chemin local resolu pour éviter les collisions entre deux dossiers de même nom situes a des emplacements differents

## Exemple de config MCP (client)

Le client MCP doit pointer vers le Python du virtual environment (et non le Python systeme) pour que le module `sive` soit trouvé.

### Activer explicitement les commandes `/sive` côté client

Le slash command est toujours gere par le client (pas par le serveur MCP). Le mapping cible doit appeler les tools MCP appropries.

Important: aucune installation pip ne peut imposer automatiquement un slash command global pour tous les LLM. Chaque client (Claude, GitHub Copilot, GPT, Gemini, etc.) doit être configure explicitement pour mapper `/sive add|list|remove|help`.

Comportement attendu du client:

- `/sive add https://playwright.dev/docs/intro` -> appel MCP `ingest(url="https://playwright.dev/docs/intro")`
- `/sive list` -> appel MCP `list_documentation_sites_in_database(include_active=True)`
- `/sive remove fastapi` -> appel MCP `delete_documentation_site(site_id="fastapi", delete_raw_files=True)`
- `/sive help` -> afficher l'aide des commandes (sans mutation)

Si votre client supporté des commandes slash personnalisees, configurez une commande `sive` qui route les sous-commandes vers les tools ci-dessus.
Si votre client ne supporté pas de slash natif, ajoutez une regle d'orchestration explicite dans ses instructions (exemple dans `MCP_SYSTEM_PROMPT` ci-dessous).

### Test rapide client pour `/sive`

Après configuration du mapping, validez ces scenarios dans le chat client:

1. Commande add URL directe:
  - `/sive add https://playwright.dev/docs/intro`
  - attendu: appel `ingest(url=...)` et retour d'un `job_id`
2. URL invalide (ex: 404):
  - `/sive add https://playwright.dev/docs`
  - attendu: retour `invalid_start_url` avec suggestion potentielle (`suggested_start_url`)
3. Commande list:
  - `/sive list`
  - attendu: inventaire des sources en base
4. Commande remove:
  - `/sive remove <doc_id>`
  - attendu: suppression de la source + fichiers bruts associés
5. Suivi de job:
  - appeler `ingest_status(job_id)` puis `wait_for_ingest_completion(job_id)` si besoin
  - attendu: progression puis statut final (`succeeded` ou `failed`)

### Configuration de base

```json
{
  "mcpServers": {
    "sive": {
      "command": "c:/Users/$user$/Workspace/SIVE/.venv/Scripts/python.exe",
      "args": ["-m", "sive", "serve"],
      "cwd": "c:/Users/$user$/Workspace/SIVE"
    }
  }
}
```

### Configuration avec instructions (Recommandé - Claude Desktop)

Pour que l'orchestrateur d'IA invoque **automatiquement** la recherche documentaire, ajoutez une instruction système :

Important:
- `MCP_SYSTEM_PROMPT` est une variable d'environnement transmise au processus MCP.
- Cette variable **ne force pas a elle seule** la politique d'orchestration du client IA.
- Pour imposer MCP-first, configurez les instructions du profil/assistant dans le client IA et désactivez Context7 (ou tout connecteur concurrent) pour ce profil/workspace.

```json
{
  "mcpServers": {
    "sive": {
      "command": "c:/Users/$user$/Workspace/SIVE/.venv/Scripts/python.exe",
      "args": ["-m", "sive", "serve"],
      "cwd": "c:/Users/$user$/Workspace/SIVE",
      "env": {
        "HF_TOKEN": "hf_xxx",
        "MCP_SYSTEM_PROMPT": "HARD RULES: 1) sive is the ONLY allowed connector for project documentation retrieval while available. 2) NEVER call Context7 (or any other doc connector) before attempting sive. 3) Before searching docs, call list_documentation_sites_in_database(include_active=True); then call search_documentation(query, topic=..., site_id=... when known). 4) Slash mapping rules: /sive add <arg> -> ingest(url=<arg>), /sive list -> list_documentation_sites_in_database(include_active=True), /sive remove <doc_id> -> delete_documentation_site(site_id=<doc_id>, delete_raw_files=True), /sive help -> help only. 5) If ingest returns multiple suggestions or needs_confirmation, ask the user which URL to use; do not choose automatically. 6) After ingestion starts, either (A) poll ingest_status(job_id) to show progress_percent/phase, or (B) call wait_for_ingest_completion(job_id) and notify user on completion. 7) If MCP has no relevant result, report that clearly and ask user whether to fallback to Context7; do not fallback automatically. 8) Final answers must cite source URLs returned by search_documentation."
      }
    }
  }
}
```

**À personnaliser :**
- Adaptez le texte du prompt a vos produits cibles et conservez la regle `MCP-first` (MCP d'abord, memoire ensuite)
- Gardez des regles de mapping explicites pour `/sive add|list|remove|help`
- Gardez le workflow explicite `list_indexed_doc_sites -> search_documentation -> ingest_status` pour les cas de mise à jour en cours
- Si votre client le permet, désactivez Context7 (ou mettez ce MCP en priorité stricte) pour éviter un routage hors de votre index.
- Optionnel: ajoutez `HF_TOKEN` (ou `HUGGINGFACE_HUB_TOKEN`) si votre environnement nécessite une auth Hub
- Remplacez `$user$` par votre nom d'utilisateur Windows
- Le chemin absolu vers `.venv/Scripts/python.exe` évite d'avoir à activer le venv manuellement

**Impact :** L'orchestrateur comprendra exactement quelles documentations sont disponibles et cherchera en priorité dans votre MCP plutôt que dans sa mémoire d'entraînement.

## Packaging et Distribution

### Construire le package

```bash
pip install build
python -m build --sdist --wheel
```

Les fichiers `.whl` et `.tar.gz` sont générés dans `dist/`.

### Publier sur PyPI

**Prérequis:**
- Compte PyPI créé sur https://pypi.org/account/register/
- Token d'authentification généré dans **Account settings -> API tokens**

**Étapes de publication:**

```bash
# 1. Nettoyer les anciens builds
rm -r build dist *.egg-info

# 2. Builder la distribution
python -m build --sdist --wheel

# 3. Vérifier les fichiers (optionnel mais recommandé)
pip install twine
twine check dist/*

# 4. Upload sur PyPI (remplacer YOUR_TOKEN par votre token)
twine upload dist/* -u __token__ -p "pypi-YOUR_TOKEN"
```

**Alternative : Configuration .pypirc**

Créez `~/.pypirc` (ou `%APPDATA%\pip\pip.ini` sur Windows):

```ini
[distutils]
index-servers = pypi

[pypi]
repository = https://upload.pypi.org/legacy/
username = __token__
password = pypi-YOUR_TOKEN_HERE
```

Puis uploadez simplement:
```bash
twine upload dist/*
```

**Test sur TestPyPI d'abord (recommandé):**

```bash
twine upload --repository testpypi dist/* -u __token__ -p "pypi-YOUR_TOKEN"
pip install -i https://test.pypi.org/simple/ --pre sive
```

**Vérifier après publication:**

- PyPI: https://pypi.org/project/SIVE/
- Installation: `pip install sive`

### Métadonnées du package

Le package inclut :
- **console script** : `sive` (accessible directement depuis le terminal après installation)
- **entry point** : `sive.__main__:main`
- **dépendances optionnelles** : `pip install -e ".[dev]"` pour développement (pytest, black, ruff, mypy)
- **classifiers PyPI** : facilite la découverte sur PyPI

## Architecture et Packaging

### Structure src-layout

Le projet utilisé la structure moderne `src-layout` pour éviter les conflits d'imports :

```
SIVE/
|- src/
|  |- sive/  (le package)
|  |  |- __init__.py
|  |  |- __main__.py       (CLI entry point)
|  |  |- auth/
|  |  |  |- __init__.py
|  |  |  |- browser.py    (crawl Playwright avec session authentifiee)
|  |  |  `- session.py    (capture de session, heuristiques login, cookies/headers)
|  |  |- config.py
|  |  |- mcp_server.py     (MCP tools)
|  |  |- scraper.py        (crawl HTML + facade de compatibilite auth)
|  |  |- scraper_auth.py   (wrapper de compatibilite deprecie)
|  |  |- scraper_auth_browser.py  (wrapper de compatibilite deprecie)
|  |  |- indexer.py
|  |  `- sites.py          (definition SiteDefinition)
|- pyproject.toml          (PEP 621)
`- README.md
```

### Avantages

- CLI directe : `sive ingest --help`
- Facilement packageable pour PyPI
- Dépendances déclarées explicitement
- Compatible avec `pip install -e .` pour développement

### PR8 (Phase 1) - Layout domain sous src

La reorganisation structurelle PR8 demarre avec des packages de domaines sous `src/sive/`:

- `app/mcp_server/`
- `domain/` (core, ingest, parse, chunk, rerank, index, runtime_state, auth, client_install)
- `infra/` (vector_store, web)
- `validation/` (e2e, benchmark)
- `compat/facades/` (wrappers de compatibilite fins)

Le comportement fonctionnel reste inchange a ce stade: ces packages servent de squelette de migration et de facades de compatibilite.

Pour lister les commandes disponibles:

```bash
python -m sive --help
```

Pour afficher les arguments de chaque sous-commande:

```bash
python -m sive scrape --help
python -m sive index --help
python -m sive ingest --help
python -m sive serve --help
```

## Auto-invocation par l'orchestrateur IA

Les descriptions des tools sont conçues pour que l'orchestrateur d'IA (Claude, ChatGPT, etc.) **invoque naturellement et automatiquement** le MCP sans que l'utilisateur doive le demander explicitement.

### Mécanisme d'auto-invocation

**Au niveau du tool (code MCP):**
- Les descriptions incluent des marqueurs visuels (`ALWAYS`, `CRITICAL`, `ESSENTIAL`) 
- Elles énumèrent explicitement les cas d'usage courants
- Elles expliquent pourquoi utiliser le tool est indispensable (évite hallucinations, info à jour, source URLs)
- Elles détaillent le workflow correct (lister sites -> chercher doc)

**Au niveau de la config client (instructions système):**
- L'env var `MCP_SYSTEM_PROMPT` ou des instructions dans le client (Claude Desktop, etc.) informent l'orchestrateur
- Listez **les noms exacts des documentations indexées** pour maximiser la pertinence
- L'orchestrateur recoit une instruction imperative: MCP d'abord, memoire ensuite seulement en fallback

### Exemple de workflow

User: "Comment configurer FastAPI ?"

-> Orchestrateur lit la config MCP et voit : "You have access to indexed documentation for: FastAPI, ..."

-> Orchestrateur appelle `list_indexed_doc_sites()` -> voir que FastAPI est disponible

-> Orchestrateur appelle `search_documentation("FastAPI configuration", site_id="fastapi")`

-> Orchestrateur retourne les résultats avec source URLs

**Résultat:** Réponse précise, à jour, avec sources vérifiables -> SANS demande explicite de l'utilisateur.

## Agent de test (Copilot)

Agent recommandé pour valider l'application de bout en bout:

- `dev-python-validation`

Role de cet agent:

- lire le code
- compiler/lancer le projet
- demander l'URL de la documentation cible et l'identite du site
- scraper et vérifier les données stockees
- vérifier que la recherche MCP exposee fonctionne correctement

Usage (dans Copilot Chat):

- lancer un sous-agent avec le nom exact `dev-python-validation`
- decrire le site a tester (site_id + URL de documentation)
- demander une validation end-to-end de l'ingestion et de la recherche MCP


