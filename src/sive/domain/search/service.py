from __future__ import annotations

from collections.abc import Callable, Iterable

from ..rerank.engine import RankedSearchResult, rank_search_results
from ..routing import find_named_site_ids
from .contracts import DocumentationSearchRepository, DocumentationSearchResponse, SearchCandidate


class DocumentationSearchService:
    def __init__(
        self,
        repository: DocumentationSearchRepository,
        *,
        normalize_topic: Callable[[str], str],
    ) -> None:
        self._repository = repository
        self._normalize_topic = normalize_topic

    def match_site_ids(self, query: str) -> tuple[str, ...]:
        return find_named_site_ids(query, self._repository.list_sites())

    def search(
        self,
        query: str,
        *,
        top_k: int,
        site_ids: Iterable[str] | None = None,
        active_site_ids: set[str] | None = None,
    ) -> DocumentationSearchResponse:
        result_limit = max(1, min(int(top_k), 20))
        requested_site_ids = tuple(dict.fromkeys(site_id.strip() for site_id in (site_ids or ()) if site_id.strip()))
        active = active_site_ids or set()
        skipped = tuple(site_id for site_id in requested_site_ids if site_id in active)
        searchable_site_ids = tuple(site_id for site_id in requested_site_ids if site_id not in active)

        candidates: list[SearchCandidate] = []
        if requested_site_ids:
            per_site_limit = min(20, max(result_limit * 2, result_limit))
            for site_id in searchable_site_ids:
                candidates.extend(
                    self._repository.query(
                        query,
                        n_results=per_site_limit,
                        site_id=site_id,
                    )
                )
        else:
            candidates = self._repository.query(
                query,
                n_results=min(20, max(result_limit * 4, result_limit)),
                excluded_site_ids=tuple(sorted(active)),
            )

        unique_candidates = self._deduplicate(candidates)
        ranked = rank_search_results(
            query,
            [candidate.document for candidate in unique_candidates],
            [candidate.metadata for candidate in unique_candidates],
            [candidate.distance for candidate in unique_candidates],
            normalize_topic=self._normalize_topic,
        )
        diversified = self._diversify(ranked, result_limit)
        searched_site_ids = searchable_site_ids or tuple(
            dict.fromkeys(
                str(result.metadata.get("site_id", "")).strip()
                for result in diversified
                if str(result.metadata.get("site_id", "")).strip()
            )
        )
        return DocumentationSearchResponse(
            results=tuple(diversified),
            searched_site_ids=searched_site_ids,
            skipped_active_site_ids=skipped,
        )

    @staticmethod
    def _deduplicate(candidates: list[SearchCandidate]) -> list[SearchCandidate]:
        seen: set[str] = set()
        unique: list[SearchCandidate] = []
        for candidate in candidates:
            identity = candidate.candidate_id or ":".join(
                (
                    str(candidate.metadata.get("site_id", "")),
                    str(candidate.metadata.get("source_url", "")),
                    str(candidate.metadata.get("chunk_index", "")),
                    str(candidate.metadata.get("section_heading", "")),
                )
            )
            if identity in seen:
                continue
            seen.add(identity)
            unique.append(candidate)
        return unique

    @staticmethod
    def _diversify(ranked: list[RankedSearchResult], limit: int) -> list[RankedSearchResult]:
        if not ranked:
            return []

        selected: list[RankedSearchResult] = []
        selected_ids: set[int] = set()
        seen_sites: set[str] = set()
        for index, result in enumerate(ranked):
            site_id = str(result.metadata.get("site_id", "")).strip()
            if site_id in seen_sites:
                continue
            selected.append(result)
            selected_ids.add(index)
            seen_sites.add(site_id)
            if len(selected) >= limit:
                return selected

        for index, result in enumerate(ranked):
            if index in selected_ids:
                continue
            selected.append(result)
            if len(selected) >= limit:
                break
        return selected
