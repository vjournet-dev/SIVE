from __future__ import annotations

from typing import Any, Protocol


class RerankStrategy(Protocol):
    name: str

    def rerank(
        self,
        query: str,
        docs: list[str],
        metas: list[dict[str, Any]],
        distances: list[float],
    ) -> tuple[list[str], list[dict[str, Any]], list[float]]:
        ...
