"""Ingest domain implementation and facades."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "IngestMethodRegistry",
    "IngestOrchestrator",
    "IngestPipelineOrchestrator",
    "IngestRequest",
    "IngestRunResult",
    "build_default_ingest_orchestrator",
    "build_default_ingest_pipeline_orchestrator",
    "load_pages_for_site",
    "run_ingest_for_site",
]


def __getattr__(name: str) -> Any:
    if name == "IngestRequest":
        module = import_module("sive.domain.ingest.contracts")
        return getattr(module, name)
    if name == "IngestMethodRegistry":
        module = import_module("sive.domain.ingest.registry")
        return getattr(module, name)
    if name in {"IngestOrchestrator", "build_default_ingest_orchestrator"}:
        module = import_module("sive.domain.ingest.orchestrator")
        return getattr(module, name)
    if name in {"IngestPipelineOrchestrator", "build_default_ingest_pipeline_orchestrator"}:
        module = import_module("sive.domain.ingest.pipeline")
        return getattr(module, name)
    if name in {"IngestRunResult", "load_pages_for_site", "run_ingest_for_site"}:
        module = import_module("sive.domain.ingest.service")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
