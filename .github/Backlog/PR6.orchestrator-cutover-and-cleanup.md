# PR6 - Orchestrator Cutover and Cleanup

## Status
- State: DONE
- Owner: Python MCP Server Expert Agent
- Depends on: PR5

## Goal
Complete the migration to a single orchestrator pipeline and remove redundant legacy paths.

## Scope
1. Runtime delegates all ingest flows to one orchestrator.
2. Remove duplicated branching logic across legacy modules.
3. Keep compatibility wrappers only where still required.

## Implementation Tasks
1. Consolidate method -> parser -> chunk -> index -> rerank sequence.
2. Keep job state lifecycle and persistence formats unchanged.
3. Mark deprecated wrappers clearly and keep them thin.

## Test Tasks
1. Orchestrator integration tests.
2. Restart and persistence recovery tests.
3. Wrapper compatibility tests.

## Mandatory Validation
1. python -m ruff check src tests
2. python -m mypy src
3. python -m pytest -q

## Acceptance Criteria
1. All ingestion flows run through one orchestrator path.
2. No MCP contract breakage.
3. State files remain compatible and restart behavior remains correct.

## Progress Log
- 2026-07-27: Added unified ingest pipeline orchestrator for method -> save -> chunk/index flow.
- 2026-07-27: Cut over ingest_service runtime path to delegate through pipeline orchestrator wrappers.
- 2026-07-27: Preserved compatibility wrappers and monkeypatch-based test behavior.
- 2026-07-27: Added orchestrator integration and wrapper compatibility regression tests.
- 2026-07-27: Validation passed (ruff, mypy, pytest).
