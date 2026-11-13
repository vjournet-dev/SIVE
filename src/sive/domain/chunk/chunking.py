from __future__ import annotations

# Chunking compatibility exports for Phase 3 while index split is staged.
from ..index.indexing import (
    _resolve_chunk_strategy,
    chunk_text,
    make_chunks,
)

__all__ = ["_resolve_chunk_strategy", "chunk_text", "make_chunks"]
