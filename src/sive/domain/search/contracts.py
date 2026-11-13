from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..rerank.engine import RankedSearchResult


@dataclass(frozen=True)
class SearchCandidate:
    candidate_id: str
    document: str
    metadata: dict[str, Any]
    distance: float


@dataclass(frozen=True)
class SearchSite:
    site_id: str
    site_name: str


@dataclass(frozen=True)
class DocumentationSearchResponse:
    results: tuple[RankedSearchResult, ...]
    searched_site_ids: tuple[str, ...]
    skipped_active_site_ids: tuple[str, ...]


class DocumentationSearchRepository(Protocol):
    def query(
        self,
        query: str,
        *,
        n_results: int,
        site_id: str | None = None,
        excluded_site_ids: tuple[str, ...] = (),
    ) -> list[SearchCandidate]:
        ...

    def list_sites(self) -> list[SearchSite]:
        ...
