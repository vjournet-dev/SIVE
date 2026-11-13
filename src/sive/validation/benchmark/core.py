from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from ...domain.rerank.engine import rerank_search_results


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    query: str
    docs: list[str]
    metas: list[dict[str, Any]]
    distances: list[float]
    expected_top_source_kind: str


def _to_float(value: Any, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def load_benchmark_cases(dataset_path: Path) -> list[BenchmarkCase]:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("dataset must be a JSON object")

    raw_cases = payload.get("cases", [])
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("dataset must define a non-empty 'cases' array")

    cases: list[BenchmarkCase] = []
    for raw in raw_cases:
        if not isinstance(raw, dict):
            continue
        case_id = str(raw.get("id", "")).strip()
        query = str(raw.get("query", "")).strip()
        expected = str(raw.get("expected_top_source_kind", "")).strip().lower()
        docs_raw = raw.get("docs", [])
        metas_raw = raw.get("metas", [])
        distances_raw = raw.get("distances", [])

        if not case_id or not query or not expected:
            raise ValueError("each case must define id, query, and expected_top_source_kind")
        if not isinstance(docs_raw, list) or not isinstance(metas_raw, list) or not isinstance(distances_raw, list):
            raise TypeError("docs, metas, and distances must be lists")
        if len(docs_raw) != len(metas_raw) or len(docs_raw) != len(distances_raw):
            raise ValueError("docs, metas, and distances must have the same length")

        docs = [str(item) for item in docs_raw]
        metas = [meta if isinstance(meta, dict) else {} for meta in metas_raw]
        distances = [_to_float(distance, default=1.0) for distance in distances_raw]

        cases.append(
            BenchmarkCase(
                case_id=case_id,
                query=query,
                docs=docs,
                metas=metas,
                distances=distances,
                expected_top_source_kind=expected,
            )
        )

    return cases


def _dcg(relevances: list[int], k: int) -> float:
    score = 0.0
    for idx, relevance in enumerate(relevances[:k], start=1):
        if relevance <= 0:
            continue
        score += (2**relevance - 1) / math.log2(idx + 1)
    return score


def _ndcg_at_k(relevances: list[int], k: int) -> float:
    observed = _dcg(relevances, k)
    ideal = _dcg(sorted(relevances, reverse=True), k)
    if ideal == 0.0:
        return 0.0
    return observed / ideal


def run_rerank_benchmark_cases(
    cases: list[BenchmarkCase],
    *,
    normalize_topic: Callable[[str], str],
    ndcg_k: int = 3,
) -> dict[str, Any]:
    if not cases:
        raise ValueError("cases must be non-empty")

    hits_at_1 = 0
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    latencies_ms: list[float] = []
    per_case: list[dict[str, Any]] = []

    for case in cases:
        start = time.perf_counter()
        docs, metas, distances = rerank_search_results(
            case.query,
            case.docs,
            case.metas,
            case.distances,
            normalize_topic=normalize_topic,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        latencies_ms.append(elapsed_ms)

        source_kinds = [str(meta.get("source_kind", "")).lower() for meta in metas]
        relevant = [1 if kind == case.expected_top_source_kind else 0 for kind in source_kinds]

        top_match = bool(source_kinds and source_kinds[0] == case.expected_top_source_kind)
        if top_match:
            hits_at_1 += 1

        rr = 0.0
        for rank, is_relevant in enumerate(relevant, start=1):
            if is_relevant:
                rr = 1.0 / rank
                break
        reciprocal_ranks.append(rr)

        ndcg = _ndcg_at_k(relevant, ndcg_k)
        ndcgs.append(ndcg)

        per_case.append(
            {
                "id": case.case_id,
                "query": case.query,
                "expected_top_source_kind": case.expected_top_source_kind,
                "predicted_top_source_kind": source_kinds[0] if source_kinds else "",
                "top_1_hit": top_match,
                "reciprocal_rank": rr,
                "ndcg": ndcg,
                "latency_ms": elapsed_ms,
                "result_count": len(docs),
                "top_distance": distances[0] if distances else None,
            }
        )

    total = len(cases)
    return {
        "dataset_size": total,
        "metrics": {
            "recall_at_1": hits_at_1 / total,
            "mrr": mean(reciprocal_ranks),
            "ndcg_at_k": ndcg_k,
            "ndcg": mean(ndcgs),
            "latency_ms_mean": mean(latencies_ms),
            "latency_ms_p95": sorted(latencies_ms)[max(0, math.ceil(0.95 * total) - 1)],
        },
        "cases": per_case,
    }
