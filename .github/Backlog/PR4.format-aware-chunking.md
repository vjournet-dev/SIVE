# PR4 - Format-Aware Chunking

## Status
- State: DONE
- Owner: Python MCP Server Expert Agent
- Depends on: PR3

## Goal
Improve chunk quality by format while preserving indexer API compatibility.

## Scope
1. Chunk strategy contract and registry.
2. Dedicated strategies for markdown, csv, xlsx, word, pdf.
3. Generic fallback strategy.

## Implementation Tasks
1. Integrate chunk strategy selection in indexing flow.
2. Preserve chunk size and overlap controls.
3. Enrich provenance metadata needed by retrieval and reranking.

## Test Tasks
1. Unit tests per chunk strategy.
2. Registry routing tests.
3. Index and ingest integration tests for chunk metadata coherence.

## Mandatory Validation
1. python -m ruff check src tests
2. python -m mypy src
3. python -m pytest -q

## Acceptance Criteria
1. Format-aware chunking is active and deterministic.
2. Fallback chunking handles unknown formats safely.
3. Existing MCP contracts remain unchanged.

## Progress Log
- 2026-07-27: Implemented format-aware chunk strategies and strategy resolution by source_kind in indexer.
- 2026-07-27: Added dedicated chunk strategy tests covering routing, fallback, and strategy behavior.
- 2026-07-27: Validation passed (ruff, mypy, pytest).
