# PR8 - Structural Rework with Domain Responsibilities (Inside /src)

## Status
- State: TODO
- Owner: Unassigned
- Depends on: PR7

## Goal
Rework the project structure so responsibilities are clearly separated by domain, while preserving behavior and compatibility.

## Mandatory Constraint
All new structure MUST be created under `/src`.

- No top-level `apps/`, `packages/`, or `tools/` outside `/src` for this rework.
- Domain boundaries must be represented by subpackages inside `src/sive/`.

## Target Structure (Required)

```text
src/
  sive/
    app/
      mcp_server/               # MCP entrypoint + tool registration wiring

    domain/
      core/                     # shared types, contracts, errors, normalization utilities
      ingest/                   # ingest orchestration and method routing
      parse/                    # format parsers (md/pdf/docx/csv/xlsx/json/html)
      chunk/                    # chunk strategies + routing
      rerank/                   # rerank strategies + routing + scoring helpers
      index/                    # indexing and incremental indexing logic
      runtime_state/            # ingest jobs lifecycle + state persistence + sync/routes
      auth/                     # authentication session and authenticated crawling
      client_install/           # skill/prompt/client MCP config generation

    infra/
      vector_store/             # Chroma-specific adapter/integration
      web/                      # HTTP/browser infrastructure adapters

    validation/
      e2e/                      # robust runtime validation entrypoints
      benchmark/                # benchmark runners + datasets

    compat/
      facades/                  # temporary compatibility wrappers (thin only)
```

## Current -> Target Mapping

1. MCP Server App
- `mcp_server.py`, `mcp_server_tools_admin.py`, `mcp_server_tools_search.py`, `mcp_server_tools_ingest.py`
- Move to: `app/mcp_server/` with thin app wiring.

2. Runtime and State
- `mcp_runtime.py`, `mcp_state.py`
- Move to: `domain/runtime_state/`.

3. Ingest Orchestration
- `ingest_service.py`, `modular_ingest/orchestrator.py`, `modular_ingest/pipeline.py`, `modular_ingest/registry.py`, `modular_ingest/adapters.py`
- Move to: `domain/ingest/`.

4. Parsing and Format Routing
- `local_loader.py`, `modular_ingest/format_registry.py`
- Move to: `domain/parse/`.

5. Chunking
- chunk logic currently in `indexer.py`, plus `modular_ingest/chunk_registry.py`
- Move to: `domain/chunk/`.

6. Reranking
- rerank logic currently in `mcp_server_core.py`, plus `modular_ingest/rerank_registry.py`, `rerank_benchmark.py`
- Move to: `domain/rerank/`.

7. Indexing
- indexing flow currently in `indexer.py`
- Move to: `domain/index/`.

8. Auth
- `auth/session.py`, `auth/browser.py`, compat wrappers `scraper_auth.py`, `scraper_auth_browser.py`
- Move domain auth into `domain/auth/`; keep thin compat wrappers under `compat/facades/`.

9. Client Install
- `skill_install.py`
- Move to: `domain/client_install/`.

10. Infrastructure
- `chroma_store.py` -> `infra/vector_store/`
- HTTP/browser adapter internals -> `infra/web/`

11. Validation and Benchmark
- `scripts/e2e_runtime_validate_robust.py` -> `validation/e2e/`
- `scripts/benchmark_rerank.py` and dataset usage -> `validation/benchmark/`

## Implementation Phases (Sequential)

### Phase 1 - Package Skeleton Under /src
1. Create target packages and `__init__.py` files under `src/sive/`.
2. Define import rules (allowed dependencies matrix) in docs.
3. Add placeholder facades to keep old imports working.

### Phase 2 - Move Runtime and Ingest Domains
1. Move runtime/state modules to `domain/runtime_state/`.
2. Move ingest orchestration to `domain/ingest/`.
3. Keep existing public imports alive via thin compatibility exports.

### Phase 3 - Move Parse/Chunk/Rerank/Index Domains
1. Split `indexer.py` responsibilities across:
   - `domain/chunk/`
   - `domain/index/`
2. Split `mcp_server_core.py` rerank parts into `domain/rerank/`.
3. Move parser logic to `domain/parse/`.

### Phase 4 - Move App/Infra/Client Install
1. Place MCP app wiring in `app/mcp_server/`.
2. Move infra adapters to `infra/`.
3. Move install generation to `domain/client_install/`.

### Phase 5 - Validation and Cleanup
1. Move runtime validation and benchmark code to `validation/` under `/src`.
2. Remove duplicated legacy paths after compatibility checks.
3. Keep only thin compatibility facades for externally used imports.

## Non-Negotiable Rules
1. `mcp_server.py` behavior and public contract must remain compatible.
2. No functional regressions in ingest/search/auth/restart behavior.
3. Compatibility wrappers must stay thin (no new business logic).
4. Every move must keep all mandatory checks green before continuing.

## Mandatory Validation (Per Phase)
1. `python -m ruff check src tests`
2. `python -m mypy src`
3. `python -m pytest -q`
4. `python scripts/e2e_runtime_validate_robust.py`

## Acceptance Criteria
1. New domain-oriented structure exists entirely under `/src`.
2. Responsibility boundaries are explicit and documented.
3. Existing MCP tool contracts are unchanged.
4. Restart/persistence/authenticated ingestion behavior is preserved.
5. Full validation gate and robust e2e pass.

## Deliverables
1. Refactored package tree under `src/sive/`.
2. Updated docs:
   - `docs/AI_ARCHITECTURE.md`
   - `README.md`
   - `DEVELOPMENT.md`
3. Updated tests for moved modules and compatibility facades.
4. Migration notes listing old import path -> new import path.

## Risks and Mitigations
1. Risk: import breakage from module moves.
   - Mitigation: staged compatibility facades + focused wiring tests.
2. Risk: hidden coupling across modules.
   - Mitigation: enforce allowed dependency matrix and incremental moves.
3. Risk: regression in async ingest lifecycle.
   - Mitigation: keep runtime tests and robust e2e in each phase.

## Suggested Work Split for Agents
1. Agent A: package skeleton + compatibility facades.
2. Agent B: runtime_state + ingest domain moves.
3. Agent C: parse/chunk/rerank/index domain split.
4. Agent D: app wiring + infra extraction + docs consolidation.
5. Agent E: validation hardening + migration notes.

## Progress Log
- 2026-07-27: Plan created for structural rework with strict `/src`-only target layout.
