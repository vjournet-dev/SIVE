from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ParsedDocument:
    source: str
    format_name: str
    title: str
    content: str
    metadata: dict[str, Any]


class FormatParserPlugin(Protocol):
    name: str

    def can_handle(self, source: str, metadata: dict[str, Any] | None = None) -> bool:
        ...

    def parse(self, source: str, payload: bytes, metadata: dict[str, Any] | None = None) -> ParsedDocument:
        ...
