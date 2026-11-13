# PR5 - Format-Aware Reranking and Benchmarks

## Status
- State: DONE
- Owner: Python MCP Server Expert Agent
- Depends on: PR4

## Goal
Increase retrieval relevance by format and measure improvements with reproducible benchmarks.

## Scope
1. Rerank strategy contract and registry.
2. Dedicated rerankers for narrative, tabular, and pdf-heavy content.
3. Benchmark harness and quality metrics.

## Implementation Tasks
1. Keep current reranking as generic fallback.
2. Route reranking by format metadata.
3. Add benchmark dataset and scripts for Recall@k, MRR, nDCG, latency.

## Test Tasks
1. Unit tests per rerank strategy.
2. Search integration tests with contract compatibility.
3. Benchmark smoke run in CI-friendly mode.

## Mandatory Validation
1. python -m ruff check src tests
2. python -m mypy src
3. python -m pytest -q

## Acceptance Criteria
1. Search response schema stays stable.
2. Benchmarks show measurable relevance gains with no critical latency regression.
3. Strategy fallback is safe for unknown formats.

## Progress Log
- 2026-07-27: Implemented format-aware reranking strategies (narrative, tabular, pdf) with safe generic fallback.
- 2026-07-27: Integrated reranking strategy routing by source_kind in mcp_server_core.rerank_search_results.
- 2026-07-27: Added reproducible benchmark harness and baseline dataset (Recall@1, MRR, nDCG, latency).
- 2026-07-27: Added benchmark smoke test and rerank strategy routing tests.
- 2026-07-27: Validation passed (ruff, mypy, pytest).
