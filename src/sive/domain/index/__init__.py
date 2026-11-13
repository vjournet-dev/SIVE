"""Index domain implementation and facades."""

from __future__ import annotations

from .indexing import index_chunks, index_pages_incrementally, make_chunks

__all__ = ["index_chunks", "index_pages_incrementally", "make_chunks"]
