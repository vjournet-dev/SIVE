from __future__ import annotations

import argparse
import json
from pathlib import Path

from sive.domain.runtime_state.state import _normalize_topic
from sive.validation.benchmark.core import load_benchmark_cases, run_rerank_benchmark_cases


def _default_dataset_path() -> Path:
    # Keep compatibility with existing dataset location in scripts/.
    scripts_dataset = Path(__file__).resolve().parents[4] / "scripts" / "benchmark_rerank_dataset.json"
    return scripts_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run format-aware reranking benchmark")
    parser.add_argument(
        "--dataset",
        default=str(_default_dataset_path()),
        help="Path to benchmark dataset JSON file.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output file path for benchmark JSON result.",
    )
    parser.add_argument(
        "--ndcg-k",
        type=int,
        default=3,
        help="Top-k used to compute nDCG.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    cases = load_benchmark_cases(dataset_path)
    result = run_rerank_benchmark_cases(cases, normalize_topic=_normalize_topic, ndcg_k=max(1, args.ndcg_k))

    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload + "\n", encoding="utf-8")
        print(f"Benchmark written to: {output_path}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
