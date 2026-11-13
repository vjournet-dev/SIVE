from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .contracts import DocumentationCatalogRepository


class DocumentationCatalogService:
    def __init__(
        self,
        repository: DocumentationCatalogRepository,
        *,
        runtime: Any,
        site_raw_docs_path: Callable[[str], Path],
        site_index_state_path: Callable[[str], Path],
    ) -> None:
        self._repository = repository
        self._runtime = runtime
        self._site_raw_docs_path = site_raw_docs_path
        self._site_index_state_path = site_index_state_path

    def indexed_sites(self, *, active_site_ids: set[str]) -> tuple[list[tuple[str, str]], list[str]]:
        sites: dict[str, str] = {}
        for metadata in self._repository.all_metadatas():
            site_id = str(metadata.get("site_id", "")).strip()
            if not site_id:
                continue
            sites[site_id] = str(metadata.get("site_name", site_id)).strip() or site_id
        visible = [(site_id, sites[site_id]) for site_id in sorted(sites) if site_id not in active_site_ids]
        hidden = sorted(site_id for site_id in active_site_ids if site_id in sites)
        return visible, hidden

    def list_sites(self, *, active_site_ids: set[str], include_active: bool) -> dict[str, Any]:
        counts: dict[str, int] = defaultdict(int)
        names: dict[str, str] = {}
        for metadata in self._repository.all_metadatas():
            site_id = str(metadata.get("site_id", "")).strip()
            if not site_id:
                continue
            counts[site_id] += 1
            names[site_id] = str(metadata.get("site_name", site_id)).strip() or site_id

        for active_site_id in active_site_ids:
            if active_site_id not in counts:
                counts[active_site_id] = 0
                names[active_site_id] = active_site_id

        items = []
        for site_id in sorted(counts):
            is_active = site_id in active_site_ids
            if not include_active and is_active:
                continue
            items.append(
                {
                    "site_id": site_id,
                    "site_name": names.get(site_id, site_id),
                    "document_count": counts[site_id],
                    "is_active_ingestion": is_active,
                }
            )
        return {
            "status": "ok",
            "total_sites": len(counts),
            "returned_sites": len(items),
            "items": items,
            "message": (
                "Documentation sites loaded from Chroma database."
                if items
                else "No documentation sites found in database."
            ),
        }

    def delete_site(self, site_id: str, *, delete_raw_files: bool) -> dict[str, Any]:
        cleaned_site_id = site_id.strip()
        if not cleaned_site_id:
            raise ValueError("site_id must be a non-empty string")

        state_result = self._runtime.remove_site_state(cleaned_site_id)
        if state_result.get("status") == "busy":
            return {
                "status": "busy",
                "site_id": cleaned_site_id,
                "active_job_ids": state_result.get("active_job_ids", []),
                "message": "Cannot delete a site while ingestion job(s) are active.",
            }

        docs_count = len(self._repository.metadatas_for_site(cleaned_site_id))
        self._repository.delete_site(cleaned_site_id)

        deleted_files: list[str] = []
        if delete_raw_files:
            for path in (
                self._site_raw_docs_path(cleaned_site_id),
                self._site_index_state_path(cleaned_site_id),
            ):
                if path.exists():
                    path.unlink()
                    deleted_files.append(str(path))

        deleted_state_entries = (
            int(state_result.get("deleted_jobs", 0))
            + int(state_result.get("deleted_routes", 0))
            + (1 if bool(state_result.get("deleted_sync", False)) else 0)
        )
        if docs_count == 0 and deleted_state_entries == 0 and not deleted_files:
            return {
                "status": "not_found",
                "site_id": cleaned_site_id,
                "deleted_docs": 0,
                "deleted_jobs": 0,
                "deleted_routes": 0,
                "deleted_sync": False,
                "deleted_files": [],
                "message": "No documentation site found for this site_id.",
            }
        return {
            "status": "ok",
            "site_id": cleaned_site_id,
            "deleted_docs": docs_count,
            "deleted_jobs": int(state_result.get("deleted_jobs", 0)),
            "deleted_routes": int(state_result.get("deleted_routes", 0)),
            "deleted_sync": bool(state_result.get("deleted_sync", False)),
            "deleted_files": deleted_files,
            "message": "Documentation site deleted from Chroma and local state.",
        }
