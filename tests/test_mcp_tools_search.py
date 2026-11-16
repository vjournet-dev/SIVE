from __future__ import annotations

from sive.app.mcp_server.tools_search import register_search_tools
from sive.domain.rerank.engine import RankedSearchResult
from sive.domain.runtime_state.state import TopicRouteRecord, TopicSiteReference
from sive.domain.search import DocumentationSearchResponse


class _FakeServer:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self, annotations=None):
        def decorator(function):
            self.tools[function.__name__] = function
            return function

        return decorator


class _FakeRuntime:
    def __init__(self, route=None, active_site_ids=None) -> None:
        self.route = route
        self._active_site_ids = active_site_ids or set()

    def find_best_topic_route(self, **_kwargs):
        return self.route

    def active_site_ids(self):
        return set(self._active_site_ids)

    def active_jobs_for_site(self, _site_id):
        return []


class _FakeSearchService:
    def __init__(self, response: DocumentationSearchResponse) -> None:
        self.response = response
        self.calls = []

    def match_site_ids(self, _query: str):
        return ()

    def search(self, query: str, **kwargs):
        self.calls.append((query, kwargs))
        return self.response


def _result(site_id: str) -> RankedSearchResult:
    return RankedSearchResult(
        document=f"Content from {site_id}",
        metadata={
            "site_id": site_id,
            "site_name": site_id,
            "source_url": f"https://{site_id}/docs",
            "title": "Docs",
            "section_heading": "Overview",
        },
        distance=0.2,
        semantic_score=0.8333,
        rank_score=1.0333,
    )


def _register(server, runtime, search_service):
    register_search_tools(
        server,
        search_service=search_service,
        runtime=runtime,
        find_best_topic_route=lambda *_args, **_kwargs: None,
        format_json=lambda payload: str(payload),
        search_doc_urls_on_web=lambda _topic, _max_results: [],
        format_search_results=lambda results: "\n".join(
            f"{result.metadata['site_id']}:{result.rank_score:.4f}" for result in results
        ),
    )


def test_search_documentation_accepts_explicit_site_ids():
    server = _FakeServer()
    service = _FakeSearchService(
        DocumentationSearchResponse(
            results=(_result("site-a"), _result("site-b")),
            searched_site_ids=("site-a", "site-b"),
            skipped_active_site_ids=(),
        )
    )
    _register(server, _FakeRuntime(), service)

    output = server.tools["search_documentation"](
        query="shared topic",
        site_ids=["site-a", "site-b", "site-a"],
    )

    assert service.calls[0][1]["site_ids"] == ("site-a", "site-b")
    assert "Sites searched: site-a, site-b." in output
    assert "site-a:1.0333" in output
    assert "site-b:1.0333" in output


def test_search_documentation_uses_all_sites_from_topic_route():
    route = TopicRouteRecord(
        topic="Shared",
        topic_key="shared",
        site_id="site-a",
        site_name="Site A",
        start_url="https://site-a/docs",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        sites=(
            TopicSiteReference("site-a", "Site A", "https://site-a/docs"),
            TopicSiteReference("site-b", "Site B", "https://site-b/docs"),
        ),
    )
    server = _FakeServer()
    service = _FakeSearchService(
        DocumentationSearchResponse(
            results=(_result("site-a"), _result("site-b")),
            searched_site_ids=("site-a", "site-b"),
            skipped_active_site_ids=(),
        )
    )
    _register(server, _FakeRuntime(route=route), service)

    output = server.tools["search_documentation"](query="shared configuration")

    assert service.calls[0][1]["site_ids"] == ("site-a", "site-b")
    assert "Topic route applied: 'Shared' -> site_ids 'site-a, site-b'." in output


def test_search_documentation_rejects_singular_and_plural_scope_together():
    server = _FakeServer()
    service = _FakeSearchService(DocumentationSearchResponse((), (), ()))
    _register(server, _FakeRuntime(), service)

    try:
        server.tools["search_documentation"](
            query="query",
            site_id="site-a",
            site_ids=["site-b"],
        )
    except ValueError as exc:
        assert "cannot be used together" in str(exc)
    else:
        raise AssertionError("Expected conflicting scopes to be rejected")
