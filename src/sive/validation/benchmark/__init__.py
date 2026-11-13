"""Benchmark validation facade."""

from __future__ import annotations

from .core import BenchmarkCase, load_benchmark_cases, run_rerank_benchmark_cases
from .rerank import main as benchmark_rerank_main

__all__ = ["BenchmarkCase", "benchmark_rerank_main", "load_benchmark_cases", "run_rerank_benchmark_cases"]
