# Copilot Instructions for sive

Mandatory pre-read before implementing any feature:

- ALWAYS read docs/AI_ARCHITECTURE.md
- ALWAYS read README.md

Do not implement, refactor, or generate feature code until both documents have been read for the current task context.

## Canonical Architecture (must follow)

The MCP server is domain-oriented under src/sive/ with this ownership model:

- app/mcp_server/: server assembly and tool wiring only
- domain/: business logic and orchestration by domain
- infra/: integrations and adapters (vector store, web)
- validation/: runtime validation and benchmarks

Public app entrypoints:

- sive.app.mcp_server.build_server
- sive.app.mcp_server.run_server

## MCP Server Change Rules

1. Keep src/sive/app/mcp_server/server.py as a thin orchestrator.
2. Register tools by concern in:
   - src/sive/app/mcp_server/tools_admin.py
   - src/sive/app/mcp_server/tools_ingest.py
   - src/sive/app/mcp_server/tools_search.py
3. Put all business logic and shared pure helpers in the appropriate `domain/` module; app tools only adapt MCP parameters and responses.
4. Keep URL discovery/refinement policy in `domain/discovery/` and external adapters in `infra/`.
5. Put ingest orchestration/service logic in src/sive/domain/ingest/.
6. Put local/remote file parsing logic in src/sive/domain/parse/.
7. Put chunking and incremental indexing logic in src/sive/domain/index/indexing.py.
8. Put runtime/job state logic in src/sive/domain/runtime_state/.
9. Put external integrations only in src/sive/infra/.
10. Inject dependencies through function parameters; avoid mutable global coupling.

## Documentation URL Scope (mandatory)

When handling a documentation URL with several path segments, do not assume that the whole host or an ancestor path is in scope.

1. Ask the user which path segment or documentation branch they want to ingest before starting the crawl.
2. If the user does not specify a branch, use the URL's last path segment as the default crawl scope.
3. If one documentation set spans several distinct URLs on the same host, ask the user to provide every branch URL to include.
4. Ingest confirmed same-host branches as one multi-URL source: one primary `url`, the other URLs in `additional_urls`, explicit `allowed_url_prefixes` for every branch, and one shared `site_id`/`site_name`.
5. Never replace explicit branch prefixes with a common parent prefix and never add unconfirmed branches.

## Migration and Compatibility Rules

- Do not reintroduce legacy root wrappers or old module paths.
- For internal code and tests, import canonical modules from app/, domain/, infra/, and validation/ packages.
- If moving an import path, update all usages in the same change set.

## Validation Gates (required)

Run after meaningful code changes:

- python -m ruff check src tests
- python -m mypy src
- python -m pytest -q

## PR Checklist

Before opening or merging a PR, confirm all items below:

- Pre-read completed: docs/AI_ARCHITECTURE.md and README.md reviewed for this task.
- File placement follows ownership boundaries (app vs domain vs infra vs validation).
- app/mcp_server/server.py remains thin (wiring/orchestration only).
- New MCP tools are registered in the correct tools_<domain>.py module.
- Shared pure logic is in the appropriate domain module; no business helper is duplicated in `app/mcp_server/`.
- No legacy module paths or compatibility wrappers were reintroduced.
- Imports were updated consistently in the same change set when paths moved.
- Validation gates pass locally: ruff, mypy, pytest.
- Tests were added or updated in the module matching production ownership.
- Public entrypoints remain stable: sive.app.mcp_server.build_server and run_server.
