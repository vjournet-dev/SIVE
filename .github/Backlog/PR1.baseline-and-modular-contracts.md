# PR1 - Baseline and Modular Contracts

## Status
- State: DONE
- Owner: Python MCP Server Expert Agent
- Branch: feature/new-architecture-ingest-method-support-format

## Goal
Freeze current behavior and introduce modular contracts without changing MCP tool outputs.

## Scope
1. Baseline current ingestion/search behavior with regression tests.
2. Add contracts for:
   - ingest method plugin
   - format parser
   - chunk strategy
   - rerank strategy
3. Add registries and adapter wiring with no behavior change.

## Implementation Tasks
1. Add contract interfaces and registries.
2. Add normalized document model and metadata schema.
3. Keep server facade thin in src/sive/mcp_server.py.
4. Route through adapters only, keep current logic active.

## Test Tasks
1. Strengthen MCP payload regression tests.
2. Add contract unit tests.
3. Validate no external behavior drift.

## Mandatory Validation
1. python -m ruff check src tests
2. python -m mypy src
3. python -m pytest -q

## Acceptance Criteria
1. MCP payloads unchanged.
2. Contracts and registries exist and are tested.
3. Architecture docs updated for the new extension points.

## Progress Log
- 2026-07-24: Added modular ingest scaffold (contracts, registry, adapters, orchestrator) and wired ingest_service through orchestrator with compatibility-preserving dependency injection.
- 2026-07-24: Validation passed (ruff, mypy, pytest): 117 passed.
- 2026-07-24: Added parser/chunker/reranker registries and deterministic fallback behavior with dedicated tests.
- 2026-07-24: Validation passed (ruff, mypy, pytest): 123 passed.
- 2026-07-24: Added MCP ingest routing contract regression tests and updated architecture guide with modular scaffold ownership.
- 2026-07-24: Final validation passed (ruff, mypy, pytest): 126 passed.
