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
Sans token, le Hub applique des limites de débit plus basses: un token accélère le
premier téléchargement, mais n'est plus utilisé une fois le modèle en cache (voir
« Démarrage et premier appel »).

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

### Installer la skill SIVE et le MCP

Après installation (uv ou pip), exécutez une fois:

```bash
sive install --target all
```

Seules les cibles `github`, `claude`, `codex` et `opencode` sont supportées.
La skill utilise le format Agent Skills: un dossier `sive` avec un `SKILL.md`
contenant le frontmatter `name` et `description`. Aucun prompt système ni fichier
d'instructions globales n'est généré.

| Cible | Skill personnelle | Configuration MCP native |
| --- | --- | --- |
| `github` (GitHub Copilot CLI) | `~/.copilot/skills/sive/SKILL.md` | `~/.copilot/mcp-config.json` |
| `claude` (Claude Code) | `~/.claude/skills/sive/SKILL.md` | `~/.claude.json` |
| `codex` | `~/.agents/skills/sive/SKILL.md` | `~/.codex/config.toml` |
| `opencode` (v2) | `~/.config/opencode/skills/sive/SKILL.md` | `~/.config/opencode/opencode.json` |

OpenCode reçoit en plus la commande `~/.config/opencode/commands/sive.md`: ses
commandes sont distinctes des skills, et `/sive <commande>` y charge la skill `sive`.

Les configurations existantes sont fusionnées: les autres serveurs et réglages
sont conservés. Le TOML conserve ses commentaires; un fichier OpenCode
`opencode.jsonc` existant est mis à jour plutôt que masqué par un nouveau JSON
(ses réglages sont conservés, mais ses commentaires sont retirés).
Une configuration invalide est signalée sans être écrasée.
Les anciens prompts installés ne sont pas supprimés automatiquement: retirez-les
des profils clients si vous les aviez activés.

Override possible vers un dossier explicite:

```bash
sive install --target github --output-dir ./out/skills
```

Important: ni uv ni pip ne permettent d'executer automatiquement un hook post-install portable pour configurer tous les clients LLM. Lancez donc `sive install` une fois après installation.

Dans ce mode par défaut, `sive install` télécharge aussi le modèle d'embedding
(`sentence-transformers/all-MiniLM-L6-v2`, ~90 Mo, une seule fois) dans le cache
Hugging Face, avec la progression affichée dans le terminal: le premier appel MCP n'a
plus à le télécharger. Un échec (réseau, proxy) n'interrompt pas l'installation: le
modèle sera téléchargé au premier appel MCP, ou relancez `sive install`. Ajoutez
`--skip-model-download` pour sauter cette étape; `--output-dir` ne télécharge rien.

Avec `--output-dir`, la commande exporte `sive/SKILL.md` et les snippets natifs:
`github.mcp.json`, `claude.mcp.json`, `codex.mcp.toml`, `opencode.mcp.json`
selon les cibles choisies. Cet export n'active pas les clients.

Par défaut, le MCP lance l'exécutable `sive` détecté dans le `PATH` (chemin absolu
résolu) avec `serve`, ou le Python courant avec `-m sive serve`. Aucun `cwd` n'est
écrit: le client lance le serveur depuis le dossier du projet ouvert. Ce dossier
n'étant pas garanti, la skill transmet les sources locales en chemins absolus.

L'installation relève aussi les délais des clients dont les défauts sont trop courts
pour un premier appel qui charge le modèle d'embedding (voir « Démarrage et premier
appel »): `startup_timeout_sec = 60` et `tool_timeout_sec = 900` pour Codex (défauts:
10 s et 60 s), `timeout: 900000` (ms) pour GitHub Copilot CLI. Claude Code et OpenCode
gardent leurs défauts; si le démarrage à froid de Claude Code dépasse 30 s, définissez
`MCP_TIMEOUT` (ms) dans l'environnement qui lance `claude`.

Vous pouvez surcharger les valeurs ecrites dans la config MCP:

```bash
sive install --target all --python-executable "C:/path/to/python.exe" --mcp-cwd "C:/path/to/project"
```

`--mcp-cwd` écrit un `cwd` explicite (ignoré pour Claude Code, dont la configuration
stdio ne supporte pas ce champ). Une réinstallation met à jour l'entrée `sive` en place:
les options ajoutées à la main (par exemple `env`) sont conservées, seules les clés
gérées par l'installateur sont réécrites et un `cwd` obsolète est retiré.

L'installateur écrit dans le dossier personnel (`~`). Si un client est configuré
ailleurs (`CODEX_HOME`, `CLAUDE_CONFIG_DIR`, `XDG_CONFIG_HOME`), générez les fichiers
avec `--output-dir` et copiez-les à l'emplacement voulu.

Rechargez les skills ou redémarrez le client après installation. Leur description
les rend disponibles pour les questions documentaires sans commande explicite:
lister les sources (une fois par conversation), choisir les identifiants réels
pertinents, rechercher une question précise sans demander de confirmation (lecture
seule), lire les extraits, puis répondre ou coder avec les références
sources. Les recherches sont ciblées par concept et séparées (en parallèle si le
client le permet) lorsque la question couvre plusieurs concepts distincts. La skill
vérifie la version ou l'état de
synchro si la fraîcheur importe. Si la documentation pertinente manque, elle
signale cette absence, propose l'ingestion d'une source pertinente, confirme son
périmètre, attend la fin puis relance la recherche. En cas d'indisponibilité du
MCP, le CLI peut servir à l'ingestion après vérification de `sive --help` et
`sive ingest --help`; il n'expose pas de commande autonome de liste ou recherche.
La sélection et les permissions des skills restent gérées par le client: ce
n'est pas une injection permanente.

### Démarrage et premier appel

`sive serve` répond au handshake MCP en quelques secondes (3 à 5 s mesurées): le modèle
d'embedding n'est plus chargé avant la réponse mais par un thread d'arrière-plan lancé
au démarrage. Le premier appel qui lit l'index (`list_documentation_sites_in_database`
ou `search_documentation`) attend la fin de ce chargement: de 15 à 30 s mesurées, davantage si le
cache disque est froid ou si le modèle est téléchargé au tout premier lancement. Les
recherches suivantes répondent en moins d'une seconde. La skill demande d'attendre ce
premier résultat sans réessayer ni se rabattre sur une autre source.

Le modèle est chargé depuis le cache local Hugging Face sans aucune requête réseau; il
n'est téléchargé que s'il manque (normalement déjà fait par `sive install`). Le serveur
ne vérifie donc pas les nouvelles révisions du modèle, ce qui garde les requêtes
cohérentes avec les vecteurs déjà indexés. L'essentiel du temps restant vient de
l'import de PyTorch et de sentence-transformers, payé une fois par processus serveur.
Le cache suit `HF_HOME` (par défaut `~/.cache/huggingface`); si vous le déplacez,
transmettez la même valeur à Codex via `env` comme `SIVE_DATA_DIR` ci-dessous, sinon
le serveur téléchargera le modèle une seconde fois dans le cache par défaut.

### Emplacement des données

L'index (`chroma/`) et les fichiers bruts et d'état (`raw/`) vivent dans un dossier de
données choisi dans cet ordre:

1. `SIVE_DATA_DIR`, s'il est défini;
2. `<dépôt>/data` pour un checkout du code source (développement);
3. sinon un dossier utilisateur qui survit aux mises à jour du package:
   `%LOCALAPPDATA%\sive` (Windows), `~/Library/Application Support/sive` (macOS),
   `$XDG_DATA_HOME/sive` ou `~/.local/share/sive` (Linux).

Une installation qui écrivait déjà dans `<package>/data` (non vide) continue de l'utiliser
tant que le dossier utilisateur n'existe pas. Les clients partagent les mêmes sources tant
qu'ils résolvent le même dossier. Codex ne transmet pas tout l'environnement aux serveurs
stdio: pour lui imposer `SIVE_DATA_DIR`, ajoutez `env = { SIVE_DATA_DIR = "..." }` à
`[mcp_servers.sive]` (conservé par `sive install`).

### Approbation des outils

Chaque outil déclare des annotations MCP: recherche, listings et statuts sont en lecture
seule, l'ingestion est non destructive et `delete_documentation_site` est destructif. Les
clients qui exploitent ces indices peuvent approuver les lectures sans invite et
redemandent confirmation avant une suppression. Pré-approbation explicite (optionnelle):

| Client | Pré-approbation |
| --- | --- |
| Claude Code | `~/.claude/settings.json`: `{"permissions": {"allow": ["mcp__sive__*"], "ask": ["mcp__sive__delete_documentation_site"]}}` |
| GitHub Copilot CLI | `copilot --allow-tool='sive'` (par session; autorise aussi la suppression) |
| Codex | rien à faire: les annotations suffisent |
| OpenCode | autorisé par défaut |

### Plusieurs clients en parallèle

Chaque client lance son propre processus `sive serve` sur le même dossier de données.
Un serveur déjà démarré voit les nouvelles sources dans les listings, mais ne les
retrouve pas dans `search_documentation` (son index vectoriel reste celui chargé au
démarrage) tant qu'il n'est pas redémarré (constaté avec chromadb 1.5.9). Après une
ingestion lancée depuis un autre client, redémarrez les sessions déjà ouvertes, et
évitez les ingestions simultanées depuis deux clients.

### Instructions globales (optionnel)

Chaque client décide lui-même quand charger une skill d'après sa description. Pour la
rendre systématique avant de coder avec une bibliothèque, ajoutez à vos instructions
globales (`CLAUDE.md`, `AGENTS.md` ou `copilot-instructions.md` selon le client) une
phrase telle que:

> Avant de répondre ou d'écrire du code qui dépend d'une bibliothèque, d'un framework,
> d'un SDK, d'une API ou d'un CLI, utilise la skill `sive` pour chercher dans la
> documentation indexée.

`sive install` ne l'écrit pas à votre place.

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
- Nouveau tool `update_documentation_source(target, max_pages=1200, delay=0.2)` pour mettre à jour une source existante par `site_id` ou chemin local indexé.
- Nouveau tool `suggest_documentation_urls(topic, max_results=5)` pour proposer des URLs de doc depuis le web quand l'utilisateur n'en fournit pas.
- Nouveau tool `ingest_and_register_topic(topic, url, ...)` pour enregistrer un sujet et lancer l'ingestion en une seule étape.
- Persistance des jobs dans `<données>/raw/ingest_jobs.json` (`<données>` = [dossier de données](#emplacement-des-données)).
- Persistance des routes sujet -> doc dans `<données>/raw/topic_routes.json`.
- Persistance du statut de synchro par site dans `<données>/raw/site_sync_state.json`.
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

Les données sont écrites dans le [dossier de données](#emplacement-des-données):

- `<données>/raw/<site_id>.jsonl`
- `<données>/raw/<site_id>.state.json`
- `<données>/chroma/`

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
- `update_documentation_source(target: str, max_pages: int = 1200, delay: float = 0.2)`
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

1. Avant chaque recherche documentaire, l'agent appelle `list_documentation_sites_in_database(include_active=True)`, choisit les vrais identifiants de sources pertinents et lance une recherche ciblée avec `site_id` ou `site_ids` (jamais les deux ensemble). Si une source est active, il vérifie son état et attend l'ingestion si nécessaire au lieu de la traiter comme un index vide. Il lit les extraits et cite leurs URLs ou références locales; les concepts distincts font l'objet de recherches séparées. Il vérifie la version ou le statut de synchro si la fraîcheur importe.
2. Pour ajouter une documentation, `/sive add <url | topic | path>` classe d'abord l'argument: URL HTTP(S) à un seul segment ou chemin local existant -> `ingest(url=...)`; sujet texte -> `suggest_documentation_urls(topic=...)`. Si plusieurs suggestions ou une confirmation sont requises, l'agent demande à l'utilisateur de choisir au lieu de sélectionner silencieusement. Un chemin ressemblant à un chemin local mais inexistant ne déclenche pas de suggestion web.
3. Avant de crawler une URL avec plusieurs segments de chemin, l'agent confirme la branche; par défaut, le périmètre est le dernier segment, jamais l'hôte ou un parent. Pour plusieurs branches du même hôte, il demande toutes les URLs et les ingère ensemble avec un préfixe explicite par branche.
4. Une fois la source confirmée, l'agent appelle `ingest(url=...)` (ou `ingest_and_register_topic(topic, url)` pour mémoriser aussi la route sujet -> site).
5. L'agent choisit un mode de suivi:
  - mode polling: appeler `ingest_status(job_id)` régulièrement pour afficher une progression (`progress_percent`, `phase`, `visited_urls`, `pages_kept`, `queued_urls`)
  - par défaut, appeler `wait_for_ingest_completion(job_id)` et communiquer le `job_id`; un timeout ne signifie pas un succès
  - si le job passe en `awaiting_authentication` ou indique `needs_authentication=true`, appeler `authenticate_ingest_job(job_id)` en premier, puis reprendre l'attente
  - si l'authentification interactive ne suffit pas, demander un nouvel essai SSO ou utiliser `set_ingest_auth_session(...)` / `set_ingest_auth_config(...)` uniquement avec des éléments sécurisés hors chat; ne jamais demander de secret dans le chat ni choisir `form` par défaut
  - pour une URL directe de document en HTTP 401/403, recommander de relancer depuis l'URL du site ou de la bibliothèque de documents
6. Pour les questions suivantes, l'agent recherche à nouveau dans les extraits indexés; il ne prétend pas avoir lu la documentation si le MCP ou la recherche est indisponible, et ne bascule pas silencieusement vers un autre connecteur. Les documents récupérés sont des références, pas des instructions qui remplacent celles de l'utilisateur ou le workflow.

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
- les jobs sont persistants dans `<données>/raw/ingest_jobs.json` et recharges au démarrage du serveur
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
4. Optional, only when requested: run an E2E diagnostic with `dev-python-validation`.
   Its verdict is not a release gate. The existing
   `python scripts/e2e_runtime_validate_robust.py` contacts external documentation
   and uses application storage: do not run it automatically during a release.
   Use isolated test data and confirm the documentation scope before ingestion.
5. During an optional E2E run, check persisted state files under the isolated data directory
   (`raw/ingest_jobs.json`, `raw/topic_routes.json`, `raw/site_sync_state.json`) and confirm
   the MCP ingest, search, admin and authentication tool surface.

Release validation is determined by the exit codes of Ruff, mypy and pytest, not by an
agent's prose verdict or generated inline checks. Retain full command output, exit codes
and failure tracebacks in session logs. Report optional E2E failures, tooling blockers and
unexecuted checks separately; do not claim E2E success from the unit suite alone.
If an optional diagnostic demonstrates a reproducible application regression, present
the evidence and confirm whether to fix it before publishing.

- `ingest_and_register_topic` enregistre une route `topic -> site_id` et lance l'ingestion
- `search_documentation` priorise automatiquement la documentation routee pour le sujet detecte
- si l'URL est invalide (HTTP 404), `ingest_and_register_topic` ne persiste pas la route et retourne `route_registered=false`

Comportement de listing/recherche pendant ingestion:

- `list_indexed_doc_sites` masque temporairement les sites en cours de scraping/indexation
- `list_documentation_sites_in_database(include_active=True)` permet aussi de lister les sources actives
- `search_documentation` reste disponible pendant ingestion
- si `search_documentation` cible explicitement un `site_id` en cours d'ingestion, un message de temporisation est retourne pour ce site

Commandes slash recommandees côté client:

- `/sive add <url | topic | path>` -> classifier l'argument, puis `ingest(...)` ou `suggest_documentation_urls(...)` selon le cas; confirmer les choix ambigus et le périmètre d'URL
- `/sive update <site_id | path>` -> `update_documentation_source(target=<argument>)`; les chemins locaux non indexés restent sans modification (`status=no_match`)
- `/sive list` -> `list_documentation_sites_in_database(include_active=True)`
- `/sive remove <doc_id>` -> `delete_documentation_site(site_id=<doc_id>, delete_raw_files=True)`
- `/sive help` -> décrit les commandes, les formats de fichiers supportés et les tools MCP, sans mutation MCP

Note pour les sources locales:

- si vous ingerez un dossier local, le `doc_id`/`site_id` visible dans les listings prendra une forme proche de `local-docs-1a2b3c4d`
- le suffixe hash est dérivé du chemin local resolu pour éviter les collisions entre deux dossiers de même nom situes a des emplacements differents

## Exemple de config MCP (client)

Le client MCP doit pointer vers le Python du virtual environment (et non le Python systeme) pour que le module `sive` soit trouvé.

### Activer explicitement les commandes `/sive` côté client

Le slash command est toujours gere par le client (pas par le serveur MCP). Le mapping cible doit appeler les tools MCP appropries.

Important: aucune installation pip ne peut imposer automatiquement un slash command global.
`sive install` déploie une skill découvrable pour GitHub Copilot CLI, Claude Code,
Codex et OpenCode v2; l'invocation explicite dépend du client (`/sive` dans Claude Code,
Copilot CLI et OpenCode via la commande installée, `$sive` dans Codex).

Comportement attendu du client:

- `/sive add https://playwright.dev/docs/intro` -> demander/confirmer la branche de documentation avant l'ingestion; restreindre le crawl au périmètre confirmé
- `/sive add Playwright` -> appeler d'abord `suggest_documentation_urls(topic="Playwright")`; demander un choix si plusieurs URLs sont proposées
- `/sive update fastapi` -> appel MCP `update_documentation_source(target="fastapi")`
- `/sive list` -> appel MCP `list_documentation_sites_in_database(include_active=True)`
- `/sive remove fastapi` -> appel MCP `delete_documentation_site(site_id="fastapi", delete_raw_files=True)`
- `/sive help` -> afficher l'aide des commandes (sans mutation)

Chargez la skill `sive` avec le mécanisme du client. Elle contient le mapping
`/sive add|update|list|remove|help`, sans prompt système supplémentaire.

### Test rapide client pour `/sive`

Après configuration du mapping, validez ces scenarios dans le chat client:

1. Commande add avec URL à plusieurs segments:
  - `/sive add https://playwright.dev/docs/intro`
  - attendu: confirmation du périmètre (par défaut le dernier segment) avant l'appel `ingest(...)`, puis retour d'un `job_id`
2. Commande add avec sujet:
  - `/sive add Playwright`
  - attendu: appel `suggest_documentation_urls(topic=...)`, puis choix utilisateur si plusieurs URLs sont retournées
3. URL invalide (ex: 404):
  - `/sive add https://playwright.dev/docs`
  - attendu: retour `invalid_start_url` avec suggestion potentielle (`suggested_start_url`)
4. Commande update:
  - `/sive update <site_id|path>`
  - attendu: appel `update_documentation_source(target=...)`; un chemin local non indexé ne crée pas de nouvelle source
5. Commande list:
  - `/sive list`
  - attendu: inventaire des sources en base
6. Commande remove:
  - `/sive remove <doc_id>`
  - attendu: suppression de la source + fichiers bruts associés
7. Suivi de job:
  - appeler `ingest_status(job_id)` puis `wait_for_ingest_completion(job_id)` si besoin
  - attendu: progression puis statut final (`succeeded` ou `failed`)

### Configuration de base (Claude Code, scope utilisateur)

```json
{
  "mcpServers": {
    "sive": {
      "type": "stdio",
      "command": "C:/path/to/SIVE/.venv/Scripts/python.exe",
      "args": ["-m", "sive", "serve"]
    }
  }
}
```

Utilisez `sive install` pour produire le format exact du client plutôt que copier
un JSON universel. GitHub utilise `mcpServers` avec `type: local`, `tools: ["*"]` et
`timeout`; Codex utilise `[mcp_servers.sive]` en TOML avec `startup_timeout_sec` et
`tool_timeout_sec`; OpenCode v2 utilise `mcp.servers.sive` avec `command` sous forme
de tableau (une ancienne entrée dépréciée `mcp.sive` est migrée automatiquement).

Formats vérifiés dans les documentations officielles:
[GitHub skills](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills),
[GitHub MCP](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers),
[Claude skills](https://code.claude.com/docs/en/skills),
[Claude MCP](https://code.claude.com/docs/en/mcp),
[Codex skills](https://developers.openai.com/codex/skills),
[Codex MCP](https://developers.openai.com/codex/mcp),
[OpenCode skills](https://opencode.ai/docs/skills/),
[OpenCode MCP](https://opencode.ai/docs/mcp-servers/).

## Packaging et Distribution

### Construire le package

```bash
pip install build
python -m build --sdist --wheel
```

Les fichiers `.whl` et `.tar.gz` sont générés dans `dist/`.

### Publier une release (recommandé)

La publication est automatisée par le workflow GitHub Actions [publish-pypi.yml](.github/workflows/publish-pypi.yml) : tout push d'un tag `v*` construit le package, le publie sur PyPI (trusted publishing) et crée la release GitHub.

Depuis le chat Copilot, utilisez le skill `release-version` : `/release <version>` (validation, bump de version, commit, tag `v<version>`, push et suivi du pipeline).

### Publier sur PyPI manuellement

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

La skill SIVE et les descriptions des tools orientent l'agent vers les sources
indexées quand de la documentation est pertinente pour la tâche.

### Mécanisme d'auto-invocation

**Au niveau du tool (code MCP):**
- Les descriptions incluent des marqueurs visuels (`ALWAYS`, `CRITICAL`, `ESSENTIAL`) 
- Elles énumèrent explicitement les cas d'usage courants
- Elles expliquent pourquoi utiliser le tool est indispensable (évite hallucinations, info à jour, source URLs)
- Elles détaillent le workflow correct (lister sites -> chercher doc)

**Au niveau de la skill client:**
- Le client découvre le frontmatter et charge `SKILL.md` lorsque pertinent.
- La skill demande d'abord l'inventaire, puis des recherches ciblées par source.
- Les extraits documentaires enrichissent le contexte avant la réponse ou le code.
- Aucune variable de prompt système ne pilote cette orchestration.

### Exemple de workflow

User: "Comment configurer FastAPI ?"

-> Le client charge la skill SIVE pour cette question de configuration.

-> Orchestrateur appelle `list_documentation_sites_in_database(include_active=True)` pour identifier FastAPI

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


