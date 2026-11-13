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
   - Discoverable Agent Skills and native client MCP configuration installation.

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

## 10. Skill Installation Service

Implementation and ownership:

- `src/sive/domain/client_install/service.py`: rendering, client-native config generation and installation.
- `src/sive/domain/client_install/skill_templates.json`: shared skill content and target mappings.
- `src/sive/__main__.py`: CLI argument adaptation only.

### 10.1 Supported targets and discovery

Only `github`, `claude`, `codex`, and `opencode` are supported; `all` selects these four.
Every target installs the same Agent Skills `sive/SKILL.md` with `name` and `description`
frontmatter. No system prompts or global instruction files are generated.

| Target | Personal skill | User MCP config | Native format |
| --- | --- | --- | --- |
| GitHub Copilot CLI (`github`) | `~/.copilot/skills/sive/SKILL.md` | `~/.copilot/mcp-config.json` | `mcpServers.sive`, `type: local`, `tools: ["*"]` |
| Claude Code (`claude`) | `~/.claude/skills/sive/SKILL.md` | `~/.claude.json` | `mcpServers.sive`, `type: stdio`, no `cwd` |
| Codex (`codex`) | `~/.agents/skills/sive/SKILL.md` | `~/.codex/config.toml` | `[mcp_servers.sive]`, `command`, `args`, `cwd` |
| OpenCode v2 (`opencode`) | `~/.config/opencode/skills/sive/SKILL.md` | `~/.config/opencode/opencode.json(c)` | `mcp.servers.sive`, `type: local`, command array, `cwd` |

Clients discover the description and load the body when relevant. Skill selection and
permissions remain client-controlled; installation does not guarantee permanent injection.
The skill follows discovery-then-query: inventory sources, select relevant identifiers,
search one concept per query, read results, cite sources, and offer scoped ingestion when
relevant documentation is missing. The CLI fallback supports ingestion, not standalone
search; retrieval still requires a connection to `sive serve`.

### 10.2 Template contract

Top-level keys:

- `shared_texts`: reusable text blocks (`ref`, `lines`, `text`, or direct strings).
- `common_render_files`: shared exported skill files.
- `targets`: only the four supported target identifiers.

Each target defines:

- `mcp_format`: selects its native config serializer.
- `mcp_output_file`: exported JSON or TOML snippet name.
- `default_install_files`: native user paths mapped to a rendered `source` or
  `special: "mcp_config"`.
- Optional `render_files`: additional rendered content.

Skill text changes require only JSON edits. Native format changes belong in the service,
not in CLI or MCP server assembly.

### 10.3 Installation behavior

`render_skill_files` returns the rendered files; `install_skill_files` exports them with
their directory structure. `install_client_mcp_configs` exports native config snippets.
Explicit output directories do not configure clients.

`install_skill_files_default_locations` resolves `sive serve` or a Python module fallback,
applies explicit Python/cwd overrides, validates existing configurations before writing,
and merges only the SIVE server into native files. Other servers and settings are retained.
TOML is parsed/updated using `tomlkit` to preserve comments and unrelated sections.
Existing OpenCode JSONC is parsed using `json5` and rewritten as valid JSON in the same
file; its settings are preserved but comments are not. Invalid configs raise explicit errors
without being overwritten. No legacy user files are deleted automatically.

### 10.4 Validation

- Focused tests: `python -m pytest -q tests/test_skill_install.py`.
- Required gates: ruff, mypy, and the complete pytest suite.
- Install smoke tests must use temporary output/home directories, never real user configs.
- Official format references are linked in README.md; OpenCode's contract targets v2.
