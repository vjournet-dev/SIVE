# Guide de Développement - sive

Ce document décrit l'environnement de développement, l'architecture du projet et les directives de contribution.

## Table des Matières

1. [Installation de Développement](#installation-de-développement)
2. [Architecture](#architecture)
3. [Structure du Projet](#structure-du-projet)
4. [Workflows de Développement](#workflows-de-développement)
5. [Tests](#tests)
6. [Lint et Formatage](#lint-et-formatage)
7. [Debugging](#debugging)
8. [Contribution](#contribution)

## Documentation IA

- Voir `docs/AI_ARCHITECTURE.md` pour la structure modulaire MCP, les conventions d'extension et la procedure d'ajout de nouveaux types d'ingestion.

## Installation de Développement

### Prérequis

- Python 3.11+
- Git
- Virtualenv (recommandé)

### Setup Initial

```bash
# Cloner le repository
git clone https://github.com/vjournet-dev/SIVE.git
cd SIVE

# Créer un virtualenv
python -m venv .venv

# Activer le virtualenv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Installer en mode développement avec dépendances dev
pip install -e ".[dev]"

# Installer le navigateur Playwright utilisé en fallback pour les sites protégés (403/429, Cloudflare, etc.)
python -m playwright install chromium
```

### Installation Reproductible (uv.lock)

Pour garantir le meme graphe de dépendances sur toutes les machines (dev, CI, uv tool), utilisez `uv.lock`.

```bash
# Depuis la racine du projet
uv sync --locked --extra dev

# Activer ensuite le virtualenv créé par uv (Windows)
.venv\Scripts\activate

# Vérifier le package MCP résolu
python -c "import importlib.metadata as md; print(md.version('mcp'))"
```

Pour installer la CLI en mode tool avec exactement cette version du projet (sans release):

```bash
uv tool uninstall sive
uv tool install "sive @ file:///C:/path/to/sive"

# Vérification rapide de la surface MCP côté tool
uv tool run --from sive python -c "import importlib.util; print(bool(importlib.util.find_spec('mcp.server.mcpserver')))"
```

Notes:
- `uv sync --locked` échoue si `pyproject.toml` et `uv.lock` divergent (comportement voulu pour la reproductibilité).
- Après changement de dépendances, regénérez le lock avec `uv lock` puis relancez `uv sync --locked`.

### Vérifier l'installation

```bash
# Afficher l'aide
sive --help

# Vérifier les imports
python -c "import sive; print('OK')"
```

## Architecture

### Composants Principaux

Le projet suit une architecture modulaire avec quatre composants clés:

```
┌─────────────────────────────────────────────────────┐
│                  MCP Server (stdio)                  │
│                (mcp_server.py - MCP)                 │
└────────────────┬─────────────────────────────────────┘
                 │
         ┌───────┴────────┐
         │                │
    ┌────▼─────┐    ┌────▼──────┐
    │ Scraper   │    │ Indexer   │
    │           │    │           │
    │ Fetch &   │    │ Chunk &   │
    │ Parse     │    │ Embed     │
    │ HTML      │    │           │
    └─────┬─────┘    └────┬──────┘
          │               │
    ┌─────▼───────────────▼─────┐
    │   Vector DB (Chroma)       │
    │   (local SQLite)           │
    └────────────────────────────┘
```

### Flux de Données

```
1. Configuration des paramètres de crawl (URL, host, path prefix)
   ↓
2. Scraper: Télécharge et parse les documentations
   ↓ (data/raw/*.jsonl)
3. Indexer: Découpe, encode, insère dans Chroma
   ↓ (data/chroma/)
4. MCP Server: Expose recherche + ingestion asynchrone
   ↓ (stdio transport)
5. Clients: Claude, autres via MCP
```

## Structure du Projet

```
SIVE/
├── src/sive/      # Code source principal
│   ├── __main__.py              # Entrypoint CLI
│   ├── chroma_store.py          # Ouverture robuste de collection Chroma
│   ├── config.py                # Modèles de configuration (Pydantic)
│   ├── ingest_service.py        # Orchestration ingest partagee CLI/MCP
│   ├── indexer.py               # Indexation vectorielle (Chroma)
│   ├── local_loader.py          # Chargement des sources locales/distantes non-HTML
│   ├── mcp_runtime.py           # Runtime jobs ingest asynchrones
│   ├── mcp_server.py            # Serveur MCP
│   ├── auth/
│   │   ├── browser.py           # Crawl Playwright avec session authentifiee
│   │   └── session.py           # Capture de session, heuristiques login, cookies/headers
│   ├── scraper.py               # Web scraper HTML + facade de compatibilite auth
│   ├── scraper_auth.py          # Wrapper de compatibilite deprecie vers auth.session
│   ├── scraper_auth_browser.py  # Wrapper de compatibilite deprecie vers auth.browser
│   ├── skill_install.py         # Installation des prompts/skills /sive
│   └── sites.py                 # Definition des structures de site
├── data/
│   ├── raw/                     # Données brutes scrapées (.jsonl + .state.json)
│   │   ├── ingest_jobs.json      # Etat persistant des jobs ingest MCP
│   │   ├── site_sync_state.json  # Etat de synchronisation par site
│   │   └── topic_routes.json     # Routage topic -> site_id
│   └── chroma/                  # Base vectorielle Chroma (SQLite)
├── tests/                       # Tests unitaires
├── pyproject.toml               # Metadata du package et dépendances
├── README.md                    # Documentation utilisateur
├── DEVELOPMENT.md              # Ce fichier
└── DEPLOYMENT.md               # Guide de déploiement
```

## Workflows de Développement

### PR8 - Structure de migration (Phase 1)

La migration structurelle PR8 introduit des packages sous `src/sive/` sans changer le comportement runtime:

- `app/mcp_server/` pour les entrees MCP
- `domain/` pour les responsabilites metier
- `infra/` pour les adaptateurs techniques
- `validation/` pour les entrypoints de validation
- `compat/facades/` pour maintenir les imports historiques

Règles importantes:

1. Les facades de compatibilite restent fines (pas de logique metier nouvelle).
2. Les nouveaux modules metier doivent cibler `domain/*`.
3. `mcp_server.py` reste une facade d'assemblage et de wiring.

### Cookbook d'extension modulaire

Checklist rapide pour etendre l'architecture sans casser les contrats:

1. Nouveau tool MCP:
   - ajouter un module `mcp_server_tools_<domain>.py`
   - exposer `register_<domain>_tools(server: FastMCP, *, ...)`
   - injecter les dependances via paramètres (pas via globals mutables)
2. Nouveau type d'ingestion:
   - ajouter detection/loader dans `local_loader.py` si source directe
   - ajouter tests local/remote associés
   - vérifier metadata normalizee (`source_kind`, sections)
3. Nouvelle strategie de chunking:
   - ajouter la strategie dans `indexer.py`
   - brancher `source_kind -> strategie` avec fallback explicite
   - ajouter tests de routage et de comportement
4. Nouvelle strategie de reranking:
   - ajouter la strategie dans `mcp_server_core.py`
   - brancher `source_kind -> strategie` avec fallback explicite
   - ajouter tests de routage/search
5. Evolution runtime ingest:
   - garder `ingest_service.py` comme facade de compatibilite
   - centraliser le flux dans `modular_ingest/pipeline.py`
   - vérifier persistance/restart dans `mcp_runtime.py`

### Playbook de readiness release

Sequence recommandée avant tag/release:

1. Gate qualite obligatoire:
   - `python -m ruff check src tests`
   - `python -m mypy src`
   - `python -m pytest -q`
2. Validation runtime robuste:
   - `python scripts/e2e_runtime_validate_robust.py`
3. Validation installation skills/config:
   - `python -m sive install --target all --output-dir <temp_dir>`
4. Verification surface MCP:
   - tools admin/search/ingest/auth exposes
   - schemas stables pour `ingest_status`, `wait_for_ingest_completion`, `search_documentation`
5. Verification persistance:
   - `data/raw/ingest_jobs.json`
   - `data/raw/topic_routes.json`
   - `data/raw/site_sync_state.json`
6. Verification docs:
   - README matrix et examples aligns au comportement réel
   - docs/AI_ARCHITECTURE.md aligne au code actuel

### Valider les nouvelles capacites MCP

Pour les changements recents, vérifier au minimum:

- Le serveur expose `ingest` et `ingest_status` en plus de `list_indexed_doc_sites` et `search_documentation`.
- `ingest` retourne immediatement un `job_id`.
- Un site protege peut basculer en `awaiting_authentication` avec `needs_authentication=true`.
- `authenticate_ingest_job`, `set_ingest_auth_session` et `set_ingest_auth_config` permettent de reprendre un job bloque par authentification.
- `list_indexed_doc_sites` masque le site pendant l'ingestion.
- `search_documentation` reste callable pendant ingestion.
- `search_documentation` avec `site_id` actif retourne un message d'attente.
- `data/raw/ingest_jobs.json` est cree/mis à jour.
- Après redémarrage serveur, un job actif est marque `failed` avec message de restart.
- `ingest` accepte aussi une source locale (fichier/dossier) en plus des URLs web.
- Les formats locaux `.csv` et `.xlsx` sont acceptes en plus de `.html`, `.htm`, `.md`, `.markdown`, `.json`, `.pdf`, `.docx`.
- Les URLs de documents distants directs (`.csv`, `.md`, `.markdown`, `.pdf`, `.docx`, `.json`, `.xlsx`) sont acceptees.
- Si un site est bloque par anti-bot (ex: challenge Cloudflare) et qu'aucune page n'est extraite, le job echoue avec un message explicite (pas de succes vide).
- Pour une source locale, `site_id` est dérivé du chemin resolu avec un suffixe hash court pour éviter les collisions entre deux répertoires de même nom.

### Modifier le Scraper

**Fichier:** `src/sive/scraper.py`

Le scraper utilisé:
- `httpx` pour les requêtes HTTP
- `BeautifulSoup4` pour le parsing HTML
- `lxml` pour la performance XPath
- `Playwright` en fallback quand un site de documentation bloque le client HTTP (ex: 403/429, challenge Cloudflare)

La logique d'authentification est maintenant decoupee:
- `src/sive/auth/session.py` pour la capture de session, les heuristiques de login et la preparation cookies/headers
- `src/sive/auth/browser.py` pour le crawl Playwright authentifie
- `src/sive/scraper.py` reste le point d'entree pour le crawl HTML et re-exporte les symboles historiques utilisés par certains tests et integrations

Le workflow d'ingestion accepte aussi des sources locales via `--start-url` ou `ingest(url=...)` quand la valeur pointe vers un chemin existant:
- fichier CSV (`.csv`)
- fichier HTML (`.html`, `.htm`)
- fichier Markdown (`.md`, `.markdown`)
- document Word (`.docx`)
- fichier JSON (`.json`)
- PDF (`.pdf`)
- fichier Excel (`.xlsx`)
- dossier contenant ces fichiers

Pour un crawl web multi-branche sur un même host, `SiteDefinition` conserve les champs singuliers historiques et expose aussi plusieurs graines/préfixes. Utilisez `--additional-start-url` et `--additional-allowed-path-prefix` côté CLI, ou `additional_urls` et `allowed_url_prefixes` avec le tool MCP `ingest`. Le crawler utilise une file commune et refuse les URL hors allowlist.

Les URLs distantes qui pointent directement vers un fichier sont aussi prises en charge pour:
- fichier CSV (`.csv`)
- fichier Markdown (`.md`, `.markdown`)
- document Word (`.docx`)
- fichier JSON (`.json`)
- PDF (`.pdf`)
- fichier Excel (`.xlsx`)

### Modifier le chargement local/distants non-HTML

**Fichiers:** `src/sive/local_loader.py`, `src/sive/ingest_service.py`

`local_loader.py` gere:
- chemins locaux vers fichiers (`.csv`, `.html`, `.htm`, `.md`, `.markdown`, `.json`, `.pdf`, `.docx`, `.xlsx`)
- chemins locaux vers dossiers (scan recursif des formats supportes)
- URLs distantes directes vers fichiers (`.csv`, `.md`, `.markdown`, `.json`, `.pdf`, `.docx`, `.xlsx`), y compris quand l'extension n'apparait plus après redirection (detection via `Content-Type` / `Content-Disposition`)
- erreurs d'authentification HTTP 401/403 sur les URLs de documents distants directs, qui sont converties en `AuthenticationRequiredError` pour permettre une reprise côté runtime MCP

Pour les sources tabulaires (`.csv`, `.xlsx`), le loader généré plusieurs niveaux de sections:
- `Summary` pour les statistiques simples par table/feuille (`row_count`, `column_count`, `*.non_empty_count`)
- `Columns` pour decrire le schema
- `Row ...` pour les lignes individuelles avec headings enrichis par les premieres valeurs discriminantes

Le rendu MCP de `search_documentation` expose aussi `Source Kind` et `Section Type`, ce qui facilite le tri humain et le reranking tabulaire.

La recherche suit maintenant une frontière stricte:

- `app/mcp_server/tools_search.py` adapte uniquement les paramètres/réponses MCP
- `domain/search/` orchestre récupération multi-sites, déduplication et diversification
- `domain/routing/` sélectionne les routes et les noms de sites
- `domain/rerank/engine.py` est l'unique moteur de pertinence utilisé par le serveur et le benchmark
- `infra/vector_store/search.py` et `catalog.py` sont les seuls adaptateurs Chroma pour ces usages

`ingest_service.py` route automatiquement la source:
- chemin local existant -> `load_local_pages(...)`
- URL de fichier distant supporté -> `load_remote_pages(...)`
- sinon -> crawl HTML classique via `scraper.py`

```python
# Ajouter un extracteur de sélecteur CSS personnalisé
from bs4 import BeautifulSoup

def extract_content(html: str) -> str:
    soup = BeautifulSoup(html, 'lxml')
    # Adapter les sélecteurs selon le site
    content = soup.select_one('.doc-content')
    return content.get_text() if content else ""
```

### Modifier l'Indexation

**Fichier:** `src/sive/indexer.py`

L'indexer utilisé:
- `sentence-transformers` pour les embeddings
- `chromadb` pour le stockage vectoriel

Pour changer le modèle d'embeddings:
```python
# Dans indexer.py
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"  # Par défaut: "all-MiniLM-L6-v2"
```

### Ajouter une Nouvelle Commande CLI

**Fichier:** `src/sive/__main__.py`

```python
import argparse

def cmd_my_new_command(args):
    """Ma nouvelle commande"""
    print(f"Exécution avec {args.param}")

# Ajouter au parser
subparsers = parser.add_subparsers(dest="command")
ingest_parser = subparsers.add_parser("my-command")
ingest_parser.add_argument("--param", required=True)
ingest_parser.set_defaults(func=cmd_my_new_command)
```

## Tests

### Exécuter les Tests

```bash
# Tous les tests
pytest

# Tests cibles utiles pour cette zone
pytest -q tests/test_scraper_browser_fallback.py
pytest -q tests/test_local_loader.py
pytest -q tests/test_mcp_runtime_authentication.py

# Avec couverture
pytest --cov=sive
```

### Ajouter des Tests

Créer des fichiers dans `tests/test_*.py`:

```python
# tests/test_scraper_browser_fallback.py
import pytest
from sive import scraper

def test_crawl_docs_requires_authentication(monkeypatch):
   # mock client / response selon le site cible
   with pytest.raises(scraper.AuthenticationRequiredError):
      scraper.crawl_docs(...)

def test_crawl_docs_uses_browser_fallback(monkeypatch):
   # mock fallback Playwright et vérifier le DocPage retourne
   ...
```

## Lint et Formatage

### Formatage du Code

```bash
# Format Black
black src/ tests/

# Formatage Ruff (import sort, linting)
ruff check src/ tests/ --fix
```

### Type Checking

```bash
# MyPy pour vérifier les types
mypy src/ tests/
```

### Avant de Committer

```bash
# Exécuter la chaîne complète
black src/ tests/
ruff check src/ tests/ --fix
mypy src/
pytest
```

## Debugging

### Logs Verbeux

```bash
# Enable debug logging (à implémenter avec logging module)
python -m sive ingest --verbose

# Ou en variable d'env
set SIVE_DEBUG=1
python -m sive ingest
```

### Inspecter la Base de Données Chroma

```bash
# Python REPL
python

>>> import chromadb
>>> client = chromadb.PersistentClient(path="data/chroma")
>>> collection = client.get_collection("documents")
>>> collection.count()
>>> results = collection.query(query_texts=["query"], n_results=5)
>>> print(results)
```

### Debugging du MCP Server

Le serveur utilisé `stdio` transport. Pour tester:

```bash
# Lancer le serveur MCP
python -m sive serve

# Puis depuis un client MCP, envoyer des requêtes
```

## Contribution

### Avant de Soumettre une PR

1. **Créer une branche feature**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Faire les modifications**
   - Modifier le code
   - Ajouter/mettre à jour les tests
   - Documenter les changements

3. **Lancer les vérifications**
   ```bash
   black src/ tests/
   ruff check src/ tests/ --fix
   mypy src/
   pytest
   ```

4. **Committer avec messages clairs**
   ```bash
   git commit -m "feat: ajouter support de X"
   git commit -m "test: ajouter tests pour Y"
   git commit -m "docs: mettre à jour le README"
   ```

5. **Pusher et soumettre une PR**
   ```bash
   git push origin feature/my-feature
   ```

### Directives de Contribution

- **Commits:** Format conventionnel (feat:, fix:, docs:, test:, etc.)
- **Tests:** Chaque fonctionnalité doit avoir des tests
- **Documentation:** Mettre à jour README.md et/ou DEVELOPMENT.md
- **Code Style:** Respecter black et ruff (vérification CI/CD)
- **Type Hints:** Ajouter des type hints à toutes les fonctions

### Convention de Nommage

- **Modules:** `lowercase_with_underscores.py`
- **Classes:** `PascalCase`
- **Fonctions/Variables:** `lowercase_with_underscores`
- **Constantes:** `UPPERCASE_WITH_UNDERSCORES`

### Commenter le Code

Pour la logique complexe, ajouter des commentaires:

```python
def complex_function():
    # Première étape: valider les inputs
    if not validate(data):
        raise ValueError("Invalid data")
    
    # Deuxième étape: transformer les données
    transformed = transform(data)
    
    return transformed
```

## Ressources

- [Modèle Sentence Transformers](https://www.sbert.net/docs/usage/semantic_search.html)
- [ChromaDB Docs](https://docs.trychroma.com/)
- [MCP Spec](https://modelcontextprotocol.io/)
- [BeautifulSoup4 Docs](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)

## Questions?

Ouvrir une issue sur [GitHub](https://github.com/vjournet-dev/SIVE/issues)
