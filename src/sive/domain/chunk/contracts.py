from __future__ import annotations

from typing import Protocol

from ..parse.contracts import ParsedDocument


class ChunkStrategy(Protocol):
    name: str

    def chunk(self, document: ParsedDocument, *, chunk_size: int, overlap: int) -> list[str]:
        ...
