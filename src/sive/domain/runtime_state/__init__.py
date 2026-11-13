"""Runtime and state domain implementation and facades."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["IngestJobRecord", "IngestRuntime", "SiteSyncRecord", "TopicRouteRecord", "TopicSiteReference"]


def __getattr__(name: str) -> Any:
	if name in {"IngestJobRecord", "SiteSyncRecord", "TopicRouteRecord", "TopicSiteReference"}:
		module = import_module("sive.domain.runtime_state.state")
		return getattr(module, name)
	if name == "IngestRuntime":
		module = import_module("sive.domain.runtime_state.runtime")
		return getattr(module, name)
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
