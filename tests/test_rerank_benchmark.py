from pathlib import Path

from sive.domain.runtime_state import state as mcp_state
from sive.validation.benchmark.core import load_benchmark_cases, run_rerank_benchmark_cases


def test_rerank_benchmark_dataset_smoke_run():
    dataset_path = Path("scripts/benchmark_rerank_dataset.json")

    cases = load_benchmark_cases(dataset_path)
    result = run_rerank_benchmark_cases(cases, normalize_topic=mcp_state._normalize_topic)

    assert result["dataset_size"] >= 1
    metrics = result["metrics"]
    assert 0.0 <= metrics["recall_at_1"] <= 1.0
    assert 0.0 <= metrics["mrr"] <= 1.0
    assert 0.0 <= metrics["ndcg"] <= 1.0
    assert metrics["latency_ms_mean"] >= 0.0
    assert metrics["latency_ms_p95"] >= 0.0
    assert len(result["cases"]) == result["dataset_size"]
