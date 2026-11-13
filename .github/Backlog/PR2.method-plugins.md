# PR2 - Method Plugins (Web, Local, Authenticated)

## Status
- State: DONE
- Owner: Python MCP Server Expert Agent
- Depends on: PR1

## Goal
Implement method plugins while keeping MCP contracts stable.

## Scope
1. Web scraping plugin.
2. Local files plugin.
3. Authenticated scraping plugin.
4. Runtime selection and delegation by source context.

## Implementation Tasks
1. Build method plugin resolver.
2. Migrate current method logic to plugin implementations.
3. Wire runtime and ingest tools to plugin-driven flow.
4. Preserve job lifecycle and persisted state format.

## Test Tasks
1. Unit tests per method plugin.
2. Runtime lifecycle integration tests.
3. MCP ingest contract regression tests.

## Mandatory Validation
1. python -m ruff check src tests
2. python -m mypy src
3. python -m pytest -q

## Acceptance Criteria
1. ingest remains asynchronous and returns job_id immediately.
2. authentication resume behavior remains intact.
3. list and search behavior during active ingestion remains intact.

## Progress Log
- 2026-07-24: Implemented explicit authenticated scraping method plugin and registered it in default orchestrator routing.
- 2026-07-24: Added method-plugin regression coverage for resolver ordering and authenticated route selection.
- 2026-07-24: Validation passed (ruff, mypy, pytest).
