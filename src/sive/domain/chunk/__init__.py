"""Chunking domain implementation and facades."""

from __future__ import annotations

from .chunking import _resolve_chunk_strategy, chunk_text, make_chunks
from .registry import ChunkStrategyRegistry

__all__ = [
    "ChunkStrategyRegistry",
    "_resolve_chunk_strategy",
    "chunk_text",
    "make_chunks",
]
