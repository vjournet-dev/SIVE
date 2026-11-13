from __future__ import annotations

from typing import Any


class ChromaDocumentationCatalogRepository:
    def __init__(self, collection: Any, *, batch_size: int = 500) -> None:
        self._collection = collection
        self._batch_size = batch_size

    @staticmethod
    def _metadatas(result: Any) -> list[dict[str, Any]]:
        if not isinstance(result, dict):
            return []
        metadatas = result.get("metadatas", [])
        if not isinstance(metadatas, list):
            return []
        return [metadata for metadata in metadatas if isinstance(metadata, dict)]

    def all_metadatas(self) -> list[dict[str, Any]]:
        try:
            total = int(self._collection.count())
        except Exception:  # noqa: BLE001 - lightweight collection doubles may not expose count
            total = -1
        if total == 0:
            return []
        if total > 0:
            metadatas: list[dict[str, Any]] = []
            for offset in range(0, total, self._batch_size):
                try:
                    result = self._collection.get(
                        include=["metadatas"],
                        limit=self._batch_size,
                        offset=offset,
                    )
                except TypeError:
                    return self._metadatas(self._collection.get(include=["metadatas"]))
                metadatas.extend(self._metadatas(result))
            return metadatas
        return self._metadatas(self._collection.get(include=["metadatas"]))

    def metadatas_for_site(self, site_id: str) -> list[dict[str, Any]]:
        try:
            result = self._collection.get(where={"site_id": site_id}, include=["metadatas"])
        except Exception:  # noqa: BLE001 - deletion still clears state when metadata lookup fails
            return []
        return self._metadatas(result)

    def delete_site(self, site_id: str) -> None:
        self._collection.delete(where={"site_id": site_id})
