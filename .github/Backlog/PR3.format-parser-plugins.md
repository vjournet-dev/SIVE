# PR3 - Format Parser Plugins (markdown, xlsx, csv, word, pdf)

## Status
- State: DONE
- Owner: Python MCP Server Expert Agent
- Depends on: PR2

## Goal
Modularize parsing by format with a normalized output model.

## Scope
1. Add parser plugins for markdown, xlsx, csv, word, pdf.
2. Add parser registry with extension and MIME routing.
3. Preserve current ingest and MCP behavior.

## Implementation Tasks
1. Implement parser contract and registry.
2. Migrate local and remote document parsing to plugins.
3. Normalize metadata for downstream chunking and reranking.
4. Keep consistent error handling for unsupported or corrupted inputs.

## Test Tasks
1. Unit tests per parser.
2. Registry resolution tests.
3. Integration tests for local and remote ingest flows.

## Mandatory Validation
1. python -m ruff check src tests
2. python -m mypy src
3. python -m pytest -q

## Acceptance Criteria
1. All 5 formats parse via dedicated plugin paths.
2. Registry fallback behavior is deterministic.
3. MCP payload compatibility preserved.

## Progress Log
- 2026-07-24: Implemented modular local and remote format parser plugins in local_loader with registry-based resolution.
- 2026-07-24: Added parser plugin coverage tests for markdown, xlsx, csv, word, pdf and alias resolution.
- 2026-07-24: Validation passed (ruff, mypy, pytest).
