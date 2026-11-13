from __future__ import annotations

from typing import Any, Protocol


class DocumentationCatalogRepository(Protocol):
    def all_metadatas(self) -> list[dict[str, Any]]:
        ...

    def metadatas_for_site(self, site_id: str) -> list[dict[str, Any]]:
        ...

    def delete_site(self, site_id: str) -> None:
        ...
