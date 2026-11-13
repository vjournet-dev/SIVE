# Implementation Roadmap - Modular Ingestion Architecture

## Purpose
This roadmap is the single source of truth for implementation status across PR1 to PR8.

## Agent Update Rule (Mandatory)
When an agent works on any PR, it must update this file in the same branch.

Required updates after each work session:
1. Update PR state in the Master Status table.
2. Add a dated entry in the Progress Timeline.
3. Update risks and blockers if any change happened.
4. Update next action and owner.

Allowed PR states:
- TODO
- IN_PROGRESS
- BLOCKED
- IN_REVIEW
- DONE

## Master Status

| PR | Title | Depends On | State | Owner | Last Update | Next Action |
|---|---|---|---|---|---|---|
| PR1 | Baseline and Modular Contracts | None | DONE | Python MCP Server Expert Agent | 2026-07-27 | Completed (commit 005ac7d) |
| PR2 | Method Plugins | PR1 | DONE | Python MCP Server Expert Agent | 2026-07-27 | Completed (commit 2e46255) |
| PR3 | Format Parser Plugins | PR2 | DONE | Python MCP Server Expert Agent | 2026-07-27 | Completed (commit 3af2680) |
| PR4 | Format-Aware Chunking | PR3 | DONE | Python MCP Server Expert Agent | 2026-07-27 | Completed |
| PR5 | Format-Aware Reranking and Benchmarks | PR4 | DONE | Python MCP Server Expert Agent | 2026-07-27 | Completed |
| PR6 | Orchestrator Cutover and Cleanup | PR5 | DONE | Python MCP Server Expert Agent | 2026-07-27 | Completed |
| PR7 | Docs, Support Matrix, and Readiness | PR6 | DONE | Python MCP Server Expert Agent | 2026-07-27 | Completed |
| PR8 | Structural Rework Under /src | PR7 | IN_PROGRESS | Python MCP Server Expert Agent | 2026-07-27 | Continue root-module migration inventory and remaining moves |

## Sequencing and Gates
1. Execute PRs in order unless an explicit exception is approved.
2. A PR can move to DONE only if all mandatory checks pass:
   - python -m ruff check src tests
   - python -m mypy src
   - python -m pytest -q
3. A dependent PR cannot move to DONE if prerequisite PR is not DONE.

## Progress Timeline
- YYYY-MM-DD - Initialization: roadmap created.
- 2026-07-24 - PR1 - State changed to IN_PROGRESS
   - Summary: Introduced modular ingest scaffold (contracts, registry, default adapters, orchestrator) and wired ingest_service through the default orchestrator path.
   - Validation: python -m ruff check src tests, python -m mypy src, python -m pytest -q (117 passed).
   - Evidence: updated src/sive/ingest_service.py and new package src/sive/modular_ingest/* plus tests/test_modular_ingest.py.
   - Next: continue PR1 by adding normalized parser/chunker/reranker registry scaffolds and baseline contract regression assertions.
- 2026-07-24 - PR1 - Registry scaffolds added
   - Summary: Added modular registries for parser, chunk strategy, and rerank strategy with deterministic resolve/fallback semantics.
   - Validation: python -m ruff check src tests, python -m mypy src, python -m pytest -q (123 passed).
   - Evidence: added src/sive/modular_ingest/format_registry.py, src/sive/modular_ingest/chunk_registry.py, src/sive/modular_ingest/rerank_registry.py, tests/test_modular_ingest_registries.py.
   - Next: add baseline MCP contract regression assertions and prepare PR1 completion review.
- 2026-07-24 - PR1 - State changed to DONE
   - Summary: Completed baseline modular architecture scaffold with compatibility-preserving wiring and added MCP ingest routing regression assertions.
   - Validation: python -m ruff check src tests, python -m mypy src, python -m pytest -q (126 passed).
   - Evidence: updated tests/test_ingest_service_contract_regression.py, docs/AI_ARCHITECTURE.md, and PR1 backlog tracking files.
   - Next: start PR2 method plugin implementation.
- 2026-07-24 - PR2 - State changed to DONE
   - Summary: Added a dedicated authenticated scraping method plugin and finalized method-plugin routing set (local, remote, authenticated, web).
   - Validation: python -m ruff check src tests, python -m mypy src, python -m pytest -q.
   - Evidence: updated src/sive/modular_ingest/adapters.py, src/sive/modular_ingest/orchestrator.py, tests/test_modular_ingest.py, and PR2 backlog tracking file.
   - Next: start PR3 parser plugin implementation.
- 2026-07-24 - PR3 - State changed to DONE
   - Summary: Modularized local and remote format parsing through registry-based parser plugins in local_loader for markdown, xlsx, csv, word, and pdf (plus existing html/json support).
   - Validation: python -m ruff check src tests, python -m mypy src, python -m pytest -q.
   - Evidence: updated src/sive/local_loader.py, added tests/test_local_loader_parser_plugins.py, and updated PR3 backlog tracking file.
   - Next: start PR4 chunk strategy implementation.
- 2026-07-27 - Roadmap audit pass
   - Summary: Reconciled roadmap with actual branch history and pushed commits for PR1, PR2, and PR3.
   - Validation: branch state checked (`feature/new-architecture-ingest-method-support-format`) and latest commits verified (005ac7d, 2e46255, 3af2680).
   - Evidence: `git log --oneline -5` and synchronized Master Status table.
   - Next: begin PR4 implementation.
- 2026-07-27 - PR4 - State changed to DONE
   - Summary: Implemented format-aware chunk strategies in indexer (markdown, csv/xlsx table, pdf, docx, fallback generic) and integrated strategy routing by source_kind.
   - Validation: python -m ruff check src tests, python -m mypy src, python -m pytest -q.
   - Evidence: updated src/sive/indexer.py, added tests/test_indexer_chunk_strategies.py, and updated PR4 backlog tracking file.
   - Next: start PR5 reranking strategy and benchmark implementation.
- 2026-07-27 - PR5 - State changed to DONE
   - Summary: Implemented format-aware rerank strategy routing in mcp_server_core with narrative/tabular/pdf strategies and generic fallback.
   - Validation: python -m ruff check src tests, python -m mypy src, python -m pytest -q.
   - Evidence: updated src/sive/mcp_server_core.py, added src/sive/rerank_benchmark.py, scripts/benchmark_rerank.py, scripts/benchmark_rerank_dataset.json, and tests.
   - Next: start PR6 orchestrator cutover and cleanup.
- 2026-07-27 - PR6 - State changed to DONE
   - Summary: Added unified ingest pipeline orchestrator and cut over ingest_service runtime path to delegate all ingestion flows through orchestrator wrappers.
   - Validation: python -m ruff check src tests, python -m mypy src, python -m pytest -q.
   - Evidence: added src/sive/modular_ingest/pipeline.py, updated src/sive/ingest_service.py and modular exports, added tests/test_ingest_pipeline_orchestrator.py and wrapper regression coverage.
   - Next: start PR7 docs/support matrix/readiness.
- 2026-07-27 - PR7 - State changed to IN_PROGRESS
   - Summary: Updated architecture docs, added explicit support matrices and release readiness playbook, and aligned robust e2e script to required MCP tool/lifecycle checks.
   - Validation: pending final gate.
   - Evidence: updated docs/AI_ARCHITECTURE.md, README.md, DEVELOPMENT.md, scripts/e2e_runtime_validate_robust.py.
   - Next: run validation gate and close PR7.
- 2026-07-27 - PR7 - State changed to DONE
   - Summary: Published final architecture/support/readiness documentation and aligned e2e runtime capability validation script.
   - Validation: python -m ruff check src tests, python -m mypy src, python -m pytest -q, python scripts/e2e_runtime_validate_robust.py (SUCCESS).
   - Evidence: updated docs/AI_ARCHITECTURE.md, README.md, DEVELOPMENT.md, scripts/e2e_runtime_validate_robust.py, and PR7 tracking files.
   - Next: roadmap PR1..PR7 implementation sequence complete.
- 2026-07-27 - PR8 - State initialized to TODO
   - Summary: Added a structural rework plan with domain-responsibility layout and strict /src-only constraint.
   - Validation: planning/documentation only.
   - Evidence: added .github/Backlog/PR8.structural-rework-src-domain-layout.md.
   - Next: begin Phase 1 package skeleton and compatibility facades under src/sive.
- 2026-07-27 - PR8 - State changed to IN_PROGRESS
   - Summary: Implemented Phase 1 package skeleton under src/sive with domain/app/infra/validation packages and thin compatibility facades.
   - Validation: python -m ruff check src tests (passed), python -m mypy src (66 files, no issues), python -m pytest -q (149 passed), python scripts/e2e_runtime_validate_robust.py (SUCCESS).
   - Evidence: added src/sive/app/*, src/sive/domain/*, src/sive/infra/*, src/sive/validation/*, src/sive/compat/facades/*, restored src/sive/domains/* compatibility wrappers, and added tests/test_domain_facades.py.
   - Next: execute Phase 2 runtime_state and ingest module moves with compatibility exports.
- 2026-07-27 - PR8 - Phase 2 runtime_state + ingest moves completed
   - Summary: Moved runtime/state and ingest implementations into domain packages (`domain/runtime_state/*`, `domain/ingest/*`) and kept legacy import paths operational through compatibility modules for `mcp_runtime.py`, `mcp_state.py`, `ingest_service.py`, and `modular_ingest/*` wrappers.
   - Validation: python -m ruff check src tests (passed), python -m mypy src (74 files, no issues), python -m pytest -q (149 passed), python scripts/e2e_runtime_validate_robust.py (SUCCESS).
   - Evidence: added `src/sive/domain/runtime_state/state.py`, `src/sive/domain/runtime_state/runtime.py`, `src/sive/domain/ingest/{contracts,adapters,registry,orchestrator,pipeline,service}.py`; updated compatibility exports in `src/sive/{mcp_runtime.py,mcp_state.py,ingest_service.py}` and `src/sive/modular_ingest/{adapters,registry,orchestrator,pipeline}.py`.
   - Next: start Phase 3 parse/chunk/rerank/index domain moves with thin compatibility exports.
- 2026-07-27 - PR8 - Phase 3 parse/chunk/rerank/index moves completed
   - Summary: Added domain implementations for parse/index/chunk/rerank (`domain/parse/*`, `domain/index/*`, `domain/chunk/chunking.py`, `domain/rerank/engine.py`) and updated facades/registries while preserving compatibility behavior for legacy modules and tests.
   - Validation: python -m ruff check src tests (passed), python -m mypy src (79 files, no issues), python -m pytest -q (149 passed), python scripts/e2e_runtime_validate_robust.py (SUCCESS).
   - Evidence: added `src/sive/domain/parse/{loader.py,format_registry.py}`, `src/sive/domain/index/indexing.py`, `src/sive/domain/chunk/chunking.py`, `src/sive/domain/rerank/engine.py`; updated `src/sive/domain/{parse,chunk,index,rerank}/__init__.py`, `src/sive/modular_ingest/format_registry.py`, and compatibility-sensitive legacy modules `src/sive/indexer.py`, `src/sive/local_loader.py`, `src/sive/mcp_server_core.py`.
   - Next: start Phase 4 app/infra/client-install moves with compatibility exports.
- 2026-07-27 - PR8 - Phase 4 started (app wiring + vector infra extraction)
   - Summary: Extracted MCP app server assembly into `app/mcp_server/server.py` and Chroma adapter logic into `infra/vector_store/chroma.py`, with legacy `mcp_server.py` and `chroma_store.py` delegating through compatibility wrappers to preserve monkeypatch/test contracts.
   - Validation: python -m ruff check src tests (passed), python -m mypy src (81 files, no issues), python -m pytest -q (149 passed), python scripts/e2e_runtime_validate_robust.py (SUCCESS).
   - Evidence: added `src/sive/app/mcp_server/server.py`, `src/sive/infra/vector_store/chroma.py`; updated `src/sive/{mcp_server.py,chroma_store.py,app/mcp_server/__init__.py,infra/vector_store/__init__.py}`.
   - Next: continue Phase 4 by moving client-install implementation into `domain/client_install/` and extracting web infra adapters under `infra/web/`.
- 2026-07-27 - PR8 - Phase 4 client-install + web infra moves completed
   - Summary: Moved client-install implementation into `domain/client_install/service.py`, converted `skill_install.py` into a thin compatibility wrapper, and routed web infrastructure exports through `infra/web/adapters.py`.
   - Validation: python -m ruff check src tests (passed), python -m mypy src (83 files, no issues), python -m pytest -q (149 passed), python scripts/e2e_runtime_validate_robust.py (SUCCESS).
   - Evidence: added `src/sive/domain/client_install/service.py` and `src/sive/infra/web/adapters.py`; updated `src/sive/{skill_install.py,domain/client_install/__init__.py,domain/__init__.py,infra/web/__init__.py}`.
   - Next: start Phase 5 validation/benchmark entrypoint moves and cleanup remaining temporary wrappers.
- 2026-07-27 - PR8 - Phase 5 validation/benchmark entrypoint moves completed
   - Summary: Moved robust runtime validation and rerank benchmark script entrypoints into `src/sive/validation/` modules and converted legacy scripts into thin compatibility wrappers.
   - Validation: python -m ruff check src tests scripts (passed), python -m mypy src (85 files, no issues), python -m pytest -q (149 passed), python scripts/e2e_runtime_validate_robust.py (SUCCESS).
   - Evidence: added `src/sive/validation/e2e/runtime_validate_robust.py` and `src/sive/validation/benchmark/rerank.py`; updated `src/sive/validation/{e2e/__init__.py,benchmark/__init__.py}` and `scripts/{e2e_runtime_validate_robust.py,benchmark_rerank.py}`.
   - Next: continue Phase 5 by auditing and removing no-longer-needed temporary compatibility wrappers while preserving external contracts.
- 2026-07-27 - PR8 - Phase 5 temporary compat wrapper cleanup completed
   - Summary: Removed the temporary `src/sive/compat/facades` package and flattened legacy `domains/*` wrappers to import directly from canonical modules while preserving legacy namespace behavior.
   - Validation: python -m ruff check src tests scripts (passed), python -m mypy src (78 files, no issues), python -m pytest -q (149 passed), python scripts/e2e_runtime_validate_robust.py (SUCCESS).
   - Evidence: deleted `src/sive/compat/{__init__.py,facades/*}`; updated `src/sive/domains/{__init__.py,client_install.py,ingestion.py,mcp_app.py,retrieval.py,runtime_state.py}` and `docs/AI_ARCHITECTURE.md`.
   - Next: prepare PR8 closure review and verify no remaining temporary compatibility layers are internal-only.
- 2026-07-27 - PR8 - Phase 5 auth domain move completed
   - Summary: Moved authentication implementation from `src/sive/auth/*` into `src/sive/domain/auth/{session.py,browser.py}` and converted root auth modules into thin compatibility wrappers.
   - Validation: python -m ruff check src tests scripts (passed), python -m mypy src (80 files, no issues), python -m pytest -q (149 passed), python scripts/e2e_runtime_validate_robust.py (SUCCESS).
   - Evidence: added `src/sive/domain/auth/{session.py,browser.py}`; updated `src/sive/{auth/session.py,auth/browser.py,domain/auth/__init__.py}`.
   - Next: continue inventory-driven migration for remaining root modules and keep compatibility wrappers only where external imports rely on them.
- 2026-07-27 - PR8 - Root ingest/index/parse/runtime modules removed (no-wrapper cut-over)
   - Summary: Rewired all internal/test imports to canonical domain modules and removed root implementations for `indexer.py`, `local_loader.py`, `ingest_service.py`, and `mcp_runtime.py`.
   - Validation: python -m ruff check src tests scripts (passed), python -m mypy src (69 files, no issues), python -m pytest -q (149 passed), python scripts/e2e_runtime_validate_robust.py (SUCCESS).
   - Evidence: deleted `src/sive/{indexer.py,local_loader.py,ingest_service.py,mcp_runtime.py}`; updated `src/sive/{__main__.py,mcp_server.py,domain/__init__.py,domain/ingest/{service.py,adapters.py},infra/web/scraper.py,domains/{__init__.py,ingestion.py,runtime_state.py}}` and related tests.
   - Next: continue removing remaining root implementation modules under MCP/discovery/benchmark surfaces.
- 2026-07-27 - PR8 - Root MCP/discovery/benchmark modules moved under app/validation
   - Summary: Moved `mcp_server_core.py`, `mcp_discovery.py`, and `mcp_server_tools_{admin,ingest,search}.py` into `app/mcp_server/` plus `rerank_benchmark.py` into `validation/benchmark/core.py`, then rewired all imports/tests to new paths.
   - Validation: python -m ruff check src tests scripts (passed), python -m mypy src (69 files, no issues), python -m pytest -q (149 passed), python scripts/e2e_runtime_validate_robust.py (SUCCESS).
   - Evidence: added `src/sive/app/mcp_server/{core.py,discovery.py,tools_admin.py,tools_ingest.py,tools_search.py}` and `src/sive/validation/benchmark/core.py`; deleted root counterparts and updated wiring in `src/sive/{mcp_server.py,domain/runtime_state/runtime.py,domain/__init__.py,domains/{__init__.py,retrieval.py},validation/benchmark/{__init__.py,rerank.py}}` plus discovery/core/benchmark tests.
   - Next: inventory remaining root modules (`config.py`, `embedding_loader.py`, `hf_auth.py`, `chroma_store.py`, `mcp_server.py`, `__main__.py`) and continue no-wrapper migration where applicable.
- 2026-07-27 - PR8 - Removed remaining internal compatibility namespaces (no-wrapper cut-over)
   - Summary: Removed `modular_ingest/*` and `domains/*` compatibility layers, moved remaining parser/chunk/rerank contracts/registries into canonical `domain/*` packages, and rewired tests/imports to direct canonical paths only.
   - Validation: python -m ruff check src tests scripts (passed), python -m mypy src (57 files, no issues), python -m pytest -q (148 passed), python scripts/e2e_runtime_validate_robust.py (SUCCESS).
   - Evidence: added `src/sive/domain/{parse/contracts.py,chunk/{contracts.py,registry.py},rerank/{contracts.py,registry.py}}`; deleted `src/sive/{modular_ingest/*,domains/*}`; updated tests `tests/{test_modular_ingest.py,test_modular_ingest_registries.py,test_ingest_pipeline_orchestrator.py,test_domain_facades.py}` and docs `docs/AI_ARCHITECTURE.md`.
   - Next: close PR8 cleanup by reviewing any residual root package indirections (lazy facades in `domain/__init__.py`), then finalize architecture docs and migration notes.

## Risks and Blockers
- None currently.

## Milestone Completion Definition
Each PR is complete only when:
1. Code scope is implemented.
2. Tests are added and passing.
3. Documentation changes for that PR are merged.
4. This roadmap is updated with the final state and evidence.

## Evidence Template
Use this template in the Progress Timeline:
- YYYY-MM-DD - PRx - State changed to IN_PROGRESS or DONE
  - Summary: short description of what changed
  - Validation: ruff or mypy or pytest results
  - Evidence: commit hash and key files changed
  - Next: next planned action
