from __future__ import annotations

from sive.infra.vector_store.search import ChromaDocumentationSearchRepository


class _PaginatedCollection:
    def __init__(self) -> None:
        self.metadatas = [
            {"site_id": f"site-{index % 3}", "site_name": f"Site {index % 3}"}
            for index in range(1200)
        ]
        self.calls = []

    def count(self):
        return len(self.metadatas)

    def get(self, *, include, limit, offset):
        self.calls.append((limit, offset))
        return {"metadatas": self.metadatas[offset : offset + limit]}


def test_list_sites_paginates_metadata_reads_and_deduplicates_sites():
    collection = _PaginatedCollection()
    repository = ChromaDocumentationSearchRepository(collection)

    sites = repository.list_sites()

    assert collection.calls == [(500, 0), (500, 500), (500, 1000)]
    assert [(site.site_id, site.site_name) for site in sites] == [
        ("site-0", "Site 0"),
        ("site-1", "Site 1"),
        ("site-2", "Site 2"),
    ]
