from __future__ import annotations

from typing import Any

from ...domain.search.contracts import SearchCandidate, SearchSite


def _first_nested_list(result: Any, key: str) -> list[Any]:
    if not isinstance(result, dict):
        return []
    value = result.get(key, [])
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else []


class ChromaDocumentationSearchRepository:
    def __init__(self, collection: Any) -> None:
        self._collection = collection

    def query(
        self,
        query: str,
        *,
        n_results: int,
        site_id: str | None = None,
        excluded_site_ids: tuple[str, ...] = (),
    ) -> list[SearchCandidate]:
        where: dict[str, Any] | None = None
        if site_id:
            where = {"site_id": site_id}
        elif excluded_site_ids:
            where = {"site_id": {"$nin": list(excluded_site_ids)}}

        result = self._collection.query(
            query_texts=[query],
            n_results=max(1, min(int(n_results), 100)),
            include=["documents", "metadatas", "distances"],
            where=where,
        )
        identifiers = _first_nested_list(result, "ids")
        documents = _first_nested_list(result, "documents")
        metadatas = _first_nested_list(result, "metadatas")
        distances = _first_nested_list(result, "distances")

        candidates: list[SearchCandidate] = []
        for index, (document, metadata, distance) in enumerate(zip(documents, metadatas, distances)):
            safe_metadata = metadata if isinstance(metadata, dict) else {}
            candidate_id = str(identifiers[index]) if index < len(identifiers) else ""
            candidates.append(
                SearchCandidate(
                    candidate_id=candidate_id,
                    document=str(document),
                    metadata=safe_metadata,
                    distance=float(distance) if isinstance(distance, (int, float)) else 1.0,
                )
            )
        return candidates

    def list_sites(self) -> list[SearchSite]:
        try:
            total = int(self._collection.count())
        except (AttributeError, TypeError, ValueError):
            total = -1

        metadatas: list[Any] = []
        if total > 0:
            for offset in range(0, total, 500):
                try:
                    result = self._collection.get(include=["metadatas"], limit=500, offset=offset)
                except TypeError:
                    result = self._collection.get(include=["metadatas"])
                    metadatas = result.get("metadatas", []) if isinstance(result, dict) else []
                    break
                if isinstance(result, dict) and isinstance(result.get("metadatas"), list):
                    metadatas.extend(result["metadatas"])
        elif total < 0:
            try:
                result = self._collection.get(include=["metadatas"])
            except (AttributeError, TypeError, ValueError):
                return []
            metadatas = result.get("metadatas", []) if isinstance(result, dict) else []

        sites: dict[str, str] = {}
        for metadata in metadatas:
            if not isinstance(metadata, dict):
                continue
            site_id = str(metadata.get("site_id", "")).strip()
            if not site_id:
                continue
            site_name = str(metadata.get("site_name", site_id)).strip() or site_id
            sites[site_id] = site_name
        return [SearchSite(site_id=site_id, site_name=sites[site_id]) for site_id in sorted(sites)]
