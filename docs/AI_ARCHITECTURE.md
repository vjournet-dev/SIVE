# AI Architecture Guide for sive

This document is designed for coding agents and contributors who need to modify server architecture safely.

## 1. Current MCP Server Architecture

The MCP server is now fully domain-oriented under `src/sive/`.

Primary app assembly:

- `app/mcp_server/__init__.py`
   - Public entrypoints: `build_server`, `run_server`.
   - Dependency wiring for app server composition.

- `app/mcp_server/server.py`
   - Thin orchestration layer only.
   - Creates FastMCP server, collection, runtime, and registers tool groups.

- `app/mcp_server/tools_admin.py`, `tools_search.py`, `tools_ingest.py`
   - Thin MCP parameter/response adapters by concern.
   - They do not query Chroma or implement business rules.

Domain ownership:

- `domain/ingest/*`
   - Ingest orchestration, pipeline contracts, and service execution.

- `domain/index/indexing.py`
   - Chunk creation and incremental indexing flow.

- `domain/parse/*`
   - Local/remote source loading and parser contracts.

- `domain/rerank/*`
   - Single canonical search result scoring, formatting and reranking engine.

- `domain/search/*`
   - Multi-site retrieval orchestration, deduplication and diversification.

- `domain/routing/*`
   - Topic normalization, multi-site route matching and explicit site-name matching.

- `domain/catalog/*`
   - Documentation inventory and deletion orchestration.

- `domain/discovery/*`
   - URL suggestion/refinement policy.

- `domain/runtime_state/*`
   - Ingest jobs lifecycle and persisted state models/helpers.

- `domain/auth/*`
   - Authentication session capture and authenticated browser crawl flow.

- `domain/client_install/*`
   - Skill/client MCP installation and prompt/config generation.

Infrastructure ownership:

- `infra/vector_store/*`
   - Chroma collection, search and catalog adapters plus embedding/auth wiring.

- `infra/web/scraper.py`
   - Crawl primitives, page extraction, and persistence helpers.

Multi-scope crawl contract:

- `SiteDefinition` keeps `start_url` and `allowed_path_prefix` for compatibility and carries optional `start_urls` and `allowed_path_prefixes` collections.
- `domain/core/sites.py` validates that combined seeds and absolute prefixes share one host and that every seed belongs to the allowlist.
- `domain/runtime_state/*` persists both singular and plural fields; legacy state without plural fields is upgraded in memory from the singular values.
- `infra/web/scraper.py` initializes one crawl queue from all seeds and admits links matching any allowed prefix, including dot-separated API namespace descendants.

URL scope decision contract:

1. URL scope selection is host-agnostic. Do not add provider-specific crawl rules.
2. Before ingesting a URL with multiple path segments, ask the user which documentation branch they want to crawl.
3. If the user does not name a branch, scope the crawl to the URL's final path segment rather than its host or a parent path.
4. When a documentation set requires several branches on the same host, ask the user to provide all branch URLs before ingesting.
5. Model the confirmed branches as one multi-URL `SiteDefinition`: retain each branch in `start_urls` and `allowed_path_prefixes`, use one `site_id`, and never broaden the allowlist to a common parent path.

Validation/benchmark ownership:

- `validation/e2e/runtime_validate_robust.py`
- `validation/benchmark/{core.py,rerank.py}`

No internal compatibility wrappers are kept for migrated root modules.

## 2. Rules for Adding a New MCP Tool Module

When adding a new tool module, use this checklist.

1. Create or extend a module under `app/mcp_server/tools_<domain>.py`.
2. Expose one registration function:
   - `register_<domain>_tools(server: FastMCP, *, ...) -> None`
3. Keep domain-specific tool definitions in that module only.
4. Inject dependencies through function parameters (runtime, formatters, helpers) instead of importing mutable globals.
5. Keep `app/mcp_server/server.py` as orchestrator only:
   - import register function
   - call register function in `build_server(...)`
6. Keep `app/mcp_server/server.py` thin and push every reusable or business rule into domain modules.
7. Validate with:
   - `python -m ruff check src tests`
   - `python -m mypy src`
   - `python -m pytest -q`

## 3. Rules for Adding a New Ingest Type

The ingest pipeline has two branches:

- Web crawl HTML: `infra/web/scraper.py`
- Local/remote direct documents: `domain/parse/loader.py`

Protected-site authentication is a cross-cutting concern owned by the auth package:

- `domain/auth/session.py` for session capture and auth heuristics
- `domain/auth/browser.py` for authenticated browser crawl

To add a new direct ingest type (example: `.xml`), do the following:

1. Add extension support constants in `domain/parse/loader.py`:
   - `SUPPORTED_LOCAL_FILE_EXTENSIONS`
   - `SUPPORTED_REMOTE_FILE_EXTENSIONS` if remote direct URL is supported.
2. Add parsers/loaders:
   - local: `_load_<type>_file(...) -> DocPage | None`
   - remote: `_load_remote_<type>(response, ...) -> DocPage | None`
3. Route file type in:
   - `load_local_pages(...)`
   - `load_remote_pages(...)`
4. Update remote type detection in `_detect_remote_file_type(...)`:
   - include MIME/content-disposition mapping.
5. Keep output normalized:
   - `DocPage`
   - sections in `DocSection`
   - meaningful `source_kind` metadata (if set during chunking/indexing).
6. Add tests in `tests/test_local_loader.py` and, if needed, ingest/runtime tests.
7. Ensure memory/safety controls are respected:
   - remote size limits (`max_bytes`) for downloaded content.

## 4. Backward-Compatibility Contract

The public app contract is intentionally small:

- `sive.app.mcp_server.build_server(...)`
- `sive.app.mcp_server.run_server()`

Internal tests target canonical domain or infrastructure modules directly. Do not introduce app-level helper facades.

Do not reintroduce removed root wrappers (for example old `mcp_server.py`, `modular_ingest/*`, `domains/*`) in internal code paths.

## 5. Refactor Safety Pattern

For architecture changes:

1. Extract pure logic first into its owning domain module.
2. Keep app server assembly thin.
3. Move tool registrations by domain.
4. Run lint, typing, tests after each extraction step.
5. Remove dead code and stale import paths in the same migration slice.

## 6. Test Layout (Focused Files)

Server-related tests are intentionally split by concern:

- `tests/test_mcp_server_wiring.py`: `build_server(...)` dependency wiring behavior
- `tests/test_mcp_discovery_helpers.py`: discovery/url-selection helper behavior
- `tests/test_mcp_server_core_helpers.py`: core helper behavior (resolve, validate, format, rerank, list/delete)
- `tests/test_mcp_state_helpers.py`: sync/state model helper behavior
- `tests/test_mcp_server_refine_start_url.py`: focused refine-start-url probing logic

When adding new tests, place them in the module matching the production ownership instead of reintroducing a monolithic `test_mcp_server.py`.

## 7. Support Matrix (Implementation Snapshot)

This matrix documents what is currently implemented in code and covered by tests.

### Ingest Source Routing

- local file/folder path -> `local_source` plugin
- remote direct document URL -> `remote_document` plugin
- web documentation URL with auth session -> `authenticated_scraping` plugin
- web documentation URL without auth session -> `web_scrape` plugin

### Supported Direct Document Formats

- local: `.csv`, `.html`, `.htm`, `.md`, `.markdown`, `.docx`, `.json`, `.pdf`, `.xlsx`
- remote direct URL: `.csv`, `.md`, `.markdown`, `.docx`, `.json`, `.pdf`, `.xlsx`

### Chunking Strategy Routing

- `markdown` -> markdown strategy
- `csv`, `xlsx` -> table strategy
- `pdf` -> pdf strategy
- `docx` -> word strategy
- unknown -> generic fallback

### Reranking Strategy Routing

- `markdown`, `html`, `docx`, `json` -> narrative strategy
- `csv`, `xlsx` -> tabular strategy
- `pdf` -> pdf strategy
- unknown -> generic fallback

## 8. PR8 Structural Rework (Phase 1 Snapshot)

PR8 established a domain-oriented layout under `src/sive/` while preserving behavior through canonical package entrypoints.

### Target package roots (Phase 1)

- `app/mcp_server/`: MCP app entrypoints and tool wiring facades
- `domain/`: domain ownership boundaries (`core`, `ingest`, `parse`, `chunk`, `rerank`, `index`, `runtime_state`, `auth`, `client_install`)
- `infra/`: implementation adapters (`vector_store`, `web`)
- `validation/`: runtime validation and benchmark entrypoint packages

### Allowed dependency matrix

Use these rules for new code placement during PR8 migration:

| From | Allowed to import | Must not import |
|---|---|---|
| `app/*` | `domain/*`, `infra/*` | direct business logic from legacy root modules unless via facade |
| `domain/*` | `domain/core`, `infra/*` | `app/*` |
| `infra/*` | `domain/core` types only | `app/*` and higher-level domain orchestration |
| `validation/*` | `app/*`, `domain/*`, `infra/*` | n/a |

### Compatibility rule for PR8

- For internal code and tests, always import canonical modules (`app/*`, `domain/*`, `infra/*`, `validation/*`).
- Do not add new compatibility wrappers for removed root modules.
- If an import path is migrated, update all usages to the new path in the same change set.

## 9. Complete File Mapping (Current Architecture)

This section is the source of truth for file placement in the canonical PR8 layout.

### 9.1 Package root

- `src/sive/__init__.py`
- `src/sive/__main__.py`
- `src/sive/config.py`

### 9.2 Application layer

- `src/sive/app/__init__.py`
- `src/sive/app/mcp_server/__init__.py`
- `src/sive/app/mcp_server/server.py`
- `src/sive/app/mcp_server/tools_admin.py`
- `src/sive/app/mcp_server/tools_ingest.py`
- `src/sive/app/mcp_server/tools_search.py`

### 9.3 Domain layer

- `src/sive/domain/__init__.py`

Core:
- `src/sive/domain/core/__init__.py`
- `src/sive/domain/core/sites.py`

Search/routing/catalog/discovery:
- `src/sive/domain/search/{contracts.py,service.py}`
- `src/sive/domain/routing/service.py`
- `src/sive/domain/catalog/{contracts.py,service.py}`
- `src/sive/domain/discovery/service.py`

Auth:
- `src/sive/domain/auth/__init__.py`
- `src/sive/domain/auth/session.py`
- `src/sive/domain/auth/browser.py`

Ingest:
- `src/sive/domain/ingest/__init__.py`
- `src/sive/domain/ingest/contracts.py`
- `src/sive/domain/ingest/registry.py`
- `src/sive/domain/ingest/adapters.py`
- `src/sive/domain/ingest/orchestrator.py`
- `src/sive/domain/ingest/pipeline.py`
- `src/sive/domain/ingest/service.py`

Parse:
- `src/sive/domain/parse/__init__.py`
- `src/sive/domain/parse/contracts.py`
- `src/sive/domain/parse/format_registry.py`
- `src/sive/domain/parse/loader.py`

Chunk:
- `src/sive/domain/chunk/__init__.py`
- `src/sive/domain/chunk/contracts.py`
- `src/sive/domain/chunk/registry.py`
- `src/sive/domain/chunk/chunking.py`

Rerank:
- `src/sive/domain/rerank/__init__.py`
- `src/sive/domain/rerank/contracts.py`
- `src/sive/domain/rerank/registry.py`
- `src/sive/domain/rerank/engine.py`

Index:
- `src/sive/domain/index/__init__.py`
- `src/sive/domain/index/indexing.py`

Runtime state:
- `src/sive/domain/runtime_state/__init__.py`
- `src/sive/domain/runtime_state/state.py`
- `src/sive/domain/runtime_state/runtime.py`

Client install:
- `src/sive/domain/client_install/__init__.py`
- `src/sive/domain/client_install/service.py`
- `src/sive/domain/client_install/skill_templates.json`

### 9.4 Infrastructure layer

- `src/sive/infra/__init__.py`

Vector store:
- `src/sive/infra/vector_store/__init__.py`
- `src/sive/infra/vector_store/chroma.py`
- `src/sive/infra/vector_store/embedding_loader.py`
- `src/sive/infra/vector_store/hf_auth.py`

Web:
- `src/sive/infra/web/__init__.py`
- `src/sive/infra/web/adapters.py`
- `src/sive/infra/web/scraper.py`

### 9.5 Validation layer

- `src/sive/validation/__init__.py`

Benchmark:
- `src/sive/validation/benchmark/__init__.py`
- `src/sive/validation/benchmark/core.py`
- `src/sive/validation/benchmark/rerank.py`

E2E:
- `src/sive/validation/e2e/__init__.py`
- `src/sive/validation/e2e/runtime_validate_robust.py`

### 9.6 Legacy to canonical migration map (complete)

Removed root module -> Canonical replacement:

- `src/sive/mcp_server.py` -> `src/sive/app/mcp_server/__init__.py`
- `src/sive/mcp_server_core.py` -> owning modules under `domain/{ingest,catalog,rerank,runtime_state}/` and `infra/vector_store/`
- `src/sive/mcp_discovery.py` -> `src/sive/domain/discovery/service.py` and `domain/core/sites.py`
- `src/sive/mcp_server_tools_admin.py` -> `src/sive/app/mcp_server/tools_admin.py`
- `src/sive/mcp_server_tools_ingest.py` -> `src/sive/app/mcp_server/tools_ingest.py`
- `src/sive/mcp_server_tools_search.py` -> `src/sive/app/mcp_server/tools_search.py`

- `src/sive/mcp_runtime.py` -> `src/sive/domain/runtime_state/runtime.py`
- `src/sive/mcp_state.py` -> `src/sive/domain/runtime_state/state.py`

- `src/sive/ingest_service.py` -> `src/sive/domain/ingest/service.py`
- `src/sive/local_loader.py` -> `src/sive/domain/parse/loader.py`
- `src/sive/indexer.py` -> `src/sive/domain/index/indexing.py`
- `src/sive/rerank_benchmark.py` -> `src/sive/validation/benchmark/core.py`

- `src/sive/sites.py` -> `src/sive/domain/core/sites.py`
- `src/sive/skill_install.py` -> `src/sive/domain/client_install/service.py`

- `src/sive/chroma_store.py` -> `src/sive/infra/vector_store/chroma.py`
- `src/sive/embedding_loader.py` -> `src/sive/infra/vector_store/embedding_loader.py`
- `src/sive/hf_auth.py` -> `src/sive/infra/vector_store/hf_auth.py`

- `src/sive/scraper.py` -> `src/sive/infra/web/scraper.py`
- `src/sive/scraper_auth.py` -> `src/sive/domain/auth/session.py`
- `src/sive/scraper_auth_browser.py` -> `src/sive/domain/auth/browser.py`

Removed package namespace -> Canonical replacement:

- `src/sive/modular_ingest/contracts.py` -> `src/sive/domain/ingest/contracts.py`
- `src/sive/modular_ingest/registry.py` -> `src/sive/domain/ingest/registry.py`
- `src/sive/modular_ingest/adapters.py` -> `src/sive/domain/ingest/adapters.py`
- `src/sive/modular_ingest/orchestrator.py` -> `src/sive/domain/ingest/orchestrator.py`
- `src/sive/modular_ingest/pipeline.py` -> `src/sive/domain/ingest/pipeline.py`

- `src/sive/modular_ingest/format_registry.py` -> `src/sive/domain/parse/format_registry.py`
- `src/sive/modular_ingest/chunk_registry.py` -> `src/sive/domain/chunk/registry.py`
- `src/sive/modular_ingest/rerank_registry.py` -> `src/sive/domain/rerank/registry.py`

Validation script mapping:

- `scripts/e2e_runtime_validate_robust.py` -> `src/sive/validation/e2e/runtime_validate_robust.py`
- `scripts/benchmark_rerank.py` -> `src/sive/validation/benchmark/rerank.py`

## 10. Skill Installation Service (New JSON-driven model)

The skill installation service is now configuration-driven.

Implementation files:

- Loader and install logic: `src/sive/domain/client_install/service.py`
- Source-of-truth templates and target mapping: `src/sive/domain/client_install/skill_templates.json`

### 10.1 Design goals

1. Modifying a skill text must require only JSON changes.
2. Adding a new LLM target must require only JSON changes.
3. Python logic should remain generic and stable.

### 10.2 JSON schema-by-convention

Top-level keys in `skill_templates.json`:

- `shared_texts`: reusable text blocks.
- `common_render_files`: files rendered for every target.
- `targets`: target-specific definitions keyed by target id (for example `copilot`, `claude`, `gpt`, `gemini`).

Each target definition includes:

- `render_files`: output file name -> text spec.
- `default_install_files`: install path -> source reference or special handler.

Text specs accepted by the loader:

- string: direct text value
- object with `ref`: reference to `shared_texts`
- object with `lines`: list of lines joined with `\n`
- object with `text`: explicit text payload

Special install handler:

- `special: "mcp_config"` instructs the service to generate MCP server config JSON instead of using a rendered text file.

### 10.3 Runtime behavior

`render_skill_files(target)`:

1. Loads templates from JSON.
2. Resolves selected targets (`all` = all keys in `targets`).
3. Merges common + target-specific rendered files.
4. Returns a `dict[file_name, content]`.

`install_skill_files(target, output_dir)`:

1. Calls `render_skill_files(target)`.
2. Writes rendered files into `output_dir`.

`install_skill_files_default_locations(target, ...)`:

1. Resolves executable command (`sive` candidates or `python -m sive serve`).
2. Builds shared `MCP_SERVER.json` payload.
3. For each selected target, applies `default_install_files` from JSON.
4. Writes either rendered content (`source`) or generated MCP config (`special: mcp_config`).

`install_client_mcp_configs(target, output_dir, ...)`:

1. Uses target selection from JSON.
2. Writes `<target>.mcp.json` for each selected target.

### 10.4 How to add a new LLM target (JSON-only)

Add a new key under `targets` in `skill_templates.json`, for example `mistral`:

1. Add `render_files` entries for prompt/instruction files.
2. Add `default_install_files` mapping for local install paths.
3. Reuse `shared_texts` via `ref` or define target-specific text.

No Python code changes are required when the new target follows this structure.

### 10.5 Validation checklist for skill install changes

After editing `skill_templates.json`:

1. Run lint on service and relevant tests.
2. Run `tests/test_skill_install.py`.
3. Optionally run a local install smoke test:
   - `sive install`

### 10.6 Concrete example: adding `mistral`

The current configuration already contains a `mistral` target. Use this as a template for future targets:

```json
{
   "targets": {
      "mistral": {
         "render_files": {
            "mistral-system-prompt.txt": {
               "ref": "system_prompt"
            }
         },
         "default_install_files": {
            ".sive/mistral/SYSTEM_PROMPT.txt": {
               "source": "mistral-system-prompt.txt"
            },
            ".sive/mistral/MCP_SERVER.json": {
               "special": "mcp_config"
            }
         }
      }
   }
}
```

To add another provider (for example `xai` or `openrouter`), duplicate this structure, change key names and output paths, and keep `special: "mcp_config"` for auto-generated MCP settings.
