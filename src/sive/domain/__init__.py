"""Domain-oriented facades for the PR8 structural layout."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "IngestRunResult",
    "IngestRuntime",
    "format_search_results",
    "install_client_mcp_configs",
    "install_skill_files",
    "install_skill_files_default_locations",
    "load_pages_for_site",
    "rerank_search_results",
    "run_ingest_for_site",
]


def __getattr__(name: str) -> Any:
    if name in {"IngestRunResult", "load_pages_for_site", "run_ingest_for_site"}:
        module = import_module("sive.domain.ingest.service")
        return getattr(module, name)
    if name == "IngestRuntime":
        module = import_module("sive.domain.runtime_state.runtime")
        return getattr(module, name)
    if name in {"format_search_results", "rerank_search_results"}:
        module = import_module("sive.domain.rerank.engine")
        return getattr(module, name)
    if name in {
        "install_client_mcp_configs",
        "install_skill_files",
        "install_skill_files_default_locations",
    }:
        module = import_module("sive.domain.client_install.service")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
