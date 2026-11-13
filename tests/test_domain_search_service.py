from __future__ import annotations

from sive.domain.routing import normalize_topic
from sive.domain.search import (
    DocumentationSearchService,
    SearchCandidate,
    SearchSite,
)


class _FakeSearchRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.by_site = {
            "site-a": [
                SearchCandidate(
                    candidate_id="a-1",
                    document="Alpha installation guide",
                    metadata={
                        "site_id": "site-a",
                        "site_name": "Alpha Docs",
                        "source_url": "https://alpha.example/install",
                        "title": "Installation",
                        "section_heading": "Setup",
                    },
                    distance=0.05,
                ),
                SearchCandidate(
                    candidate_id="a-2",
                    document="Alpha advanced setup",
                    metadata={
                        "site_id": "site-a",
                        "site_name": "Alpha Docs",
                        "source_url": "https://alpha.example/advanced",
                        "title": "Advanced",
                        "section_heading": "Setup",
                    },
                    distance=0.08,
                ),
            ],
            "site-b": [
                SearchCandidate(
                    candidate_id="b-1",
                    document="Beta installation guide",
                    metadata={
                        "site_id": "site-b",
                        "site_name": "Beta Manual",
                        "source_url": "https://beta.example/install",
                        "title": "Installation",
                        "section_heading": "Setup",
                    },
                    distance=0.2,
                )
            ],
        }

    def query(self, query: str, *, n_results: int, site_id=None, excluded_site_ids=()):
        self.calls.append(
            {
                "query": query,
                "n_results": n_results,
                "site_id": site_id,
                "excluded_site_ids": excluded_site_ids,
            }
        )
        if site_id:
            return list(self.by_site.get(site_id, []))
        return [
            candidate
            for candidate_site_id, candidates in self.by_site.items()
            if candidate_site_id not in excluded_site_ids
            for candidate in candidates
        ]

    def list_sites(self):
        return [SearchSite("site-a", "Alpha Docs"), SearchSite("site-b", "Beta Manual")]


def test_search_queries_each_selected_site_and_diversifies_top_results():
    repository = _FakeSearchRepository()
    service = DocumentationSearchService(repository, normalize_topic=normalize_topic)

    response = service.search(
        "installation setup",
        top_k=2,
        site_ids=["site-a", "site-b"],
    )

    assert [call["site_id"] for call in repository.calls] == ["site-a", "site-b"]
    assert {result.metadata["site_id"] for result in response.results} == {"site-a", "site-b"}
    assert response.searched_site_ids == ("site-a", "site-b")
    assert all(result.rank_score >= result.semantic_score for result in response.results)


def test_search_skips_active_selected_site_without_blocking_other_sites():
    repository = _FakeSearchRepository()
    service = DocumentationSearchService(repository, normalize_topic=normalize_topic)

    response = service.search(
        "installation",
        top_k=5,
        site_ids=["site-a", "site-b"],
        active_site_ids={"site-a"},
    )

    assert [call["site_id"] for call in repository.calls] == ["site-b"]
    assert response.searched_site_ids == ("site-b",)
    assert response.skipped_active_site_ids == ("site-a",)


def test_search_excludes_active_sites_from_global_query():
    repository = _FakeSearchRepository()
    service = DocumentationSearchService(repository, normalize_topic=normalize_topic)

    response = service.search("installation", top_k=5, active_site_ids={"site-a"})

    assert repository.calls[0]["excluded_site_ids"] == ("site-a",)
    assert {result.metadata["site_id"] for result in response.results} == {"site-b"}


def test_match_site_ids_uses_explicit_site_name_or_identifier():
    service = DocumentationSearchService(_FakeSearchRepository(), normalize_topic=normalize_topic)

    assert service.match_site_ids("How do I configure Alpha Docs?") == ("site-a",)
    assert service.match_site_ids("Compare site-a with Beta Manual") == ("site-b", "site-a")
    assert service.match_site_ids("How do I install this library?") == ()
