from sive.domain.core import sites as domain_sites
from sive.domain.discovery import service as discovery_service
from sive.domain.runtime_state import runtime as mcp_runtime
from sive.domain.runtime_state import state as mcp_state


def test_search_doc_urls_on_web_returns_extracted_candidates():
    captured: dict[str, object] = {"queries": []}

    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query: str, max_results: int):
            captured["queries"].append(query)
            captured["max_results"] = max_results
            return [
                {"title": "FastAPI docs", "href": "https://fastapi.tiangolo.com/"},
                {"title": "Duplicate", "href": "https://fastapi.tiangolo.com"},
                {"title": "Not docs", "href": "https://example.com/blog/post"},
                {"title": "API reference", "href": "https://example.com/api/reference"},
            ]

    result = discovery_service.search_documentation_urls(
        "fastapi",
        3,
        ddgs_factory=lambda: FakeDDGS(),
        refine_url=lambda url: "https://fastapi.tiangolo.com/docs/intro" if "fastapi.tiangolo.com" in url else url,
    )

    assert result == [
        {"title": "FastAPI docs", "url": "https://fastapi.tiangolo.com/docs/intro"},
        {"title": "API reference", "url": "https://example.com/api/reference"},
    ]
    assert captured["queries"][0] == "fastapi official documentation"
    assert captured["max_results"] == 12


def test_search_doc_urls_on_web_filters_root_like_urls():
    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query: str, max_results: int):
            return [
                {"title": "Root docs", "href": "https://example.com/docs"},
                {"title": "Root host", "href": "https://example.com/"},
            ]

    result = discovery_service.search_documentation_urls(
        "example",
        5,
        ddgs_factory=lambda: FakeDDGS(),
        refine_url=lambda url: url,
    )

    assert result == []


def test_search_doc_urls_on_web_returns_empty_list_on_ddgs_error():
    class FailingDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query: str, max_results: int):
            raise RuntimeError("search failed")

    result = discovery_service.search_documentation_urls(
        "fastapi",
        5,
        ddgs_factory=lambda: FailingDDGS(),
        refine_url=lambda url: url,
    )

    assert result == []


def test_search_doc_urls_on_web_no_recursion_with_default_refine():
    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query: str, max_results: int):
            return [{"title": "Intro docs", "href": "https://example.com/docs/intro"}]

    result = discovery_service.search_documentation_urls(
        "example",
        5,
        ddgs_factory=lambda: FakeDDGS(),
        refine_url=lambda url: url,
    )

    assert result == [{"title": "Intro docs", "url": "https://example.com/docs/intro"}]


def test_search_doc_urls_on_web_prioritizes_official_vendor_docs_over_aggregators():
    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query: str, max_results: int):
            return [
                {"title": "Community guide", "href": "https://medium.com/@someone/awesomelib-guide"},
                {"title": "AwesomeLib docs", "href": "https://awesomelib.dev/docs/getting-started"},
                {"title": "AwesomeLib API", "href": "https://awesomelib.dev/docs/api/reference"},
            ]

    result = discovery_service.search_documentation_urls(
        "awesomelib",
        2,
        ddgs_factory=lambda: FakeDDGS(),
        refine_url=lambda url: url,
    )

    assert result[0]["url"] == "https://awesomelib.dev/docs/getting-started"
    assert all("medium.com" not in item["url"] for item in result)


def test_search_doc_urls_on_web_retries_ddgs_with_alternate_query_templates():
    captured_queries: list[str] = []

    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query: str, max_results: int):
            captured_queries.append(query)
            if len(captured_queries) == 1:
                return []
            return [{"title": "Numpy docs", "href": "https://numpy.org/doc/stable/getting-started"}]

    result = discovery_service.search_documentation_urls(
        "numpy",
        1,
        ddgs_factory=lambda: FakeDDGS(),
        refine_url=lambda url: url,
    )

    assert result == [{"title": "Numpy docs", "url": "https://numpy.org/doc/stable/getting-started"}]
    assert captured_queries == [
        "numpy official documentation",
        "numpy documentation",
    ]


def test_site_from_latest_job_prefers_most_recent_started_job():
    jobs = {
        "job-old": mcp_state.IngestJobRecord(
            job_id="job-old",
            site_id="playwright-dev-docs",
            site_name="playwright.dev",
            start_url="https://playwright.dev/docs/intro",
            allowed_host="playwright.dev",
            allowed_path_prefix="/docs/",
            status="succeeded",
            phase="completed",
            created_at="2026-07-12T10:00:00+00:00",
            incremental=True,
            max_pages=1200,
            delay=0.2,
            started_at="2026-07-12T10:00:10+00:00",
        ),
        "job-new": mcp_state.IngestJobRecord(
            job_id="job-new",
            site_id="playwright-dev-docs",
            site_name="playwright.dev",
            start_url="https://playwright.dev/docs/getting-started",
            allowed_host="playwright.dev",
            allowed_path_prefix="/docs/",
            status="succeeded",
            phase="completed",
            created_at="2026-07-13T10:00:00+00:00",
            incremental=True,
            max_pages=1200,
            delay=0.2,
            started_at="2026-07-13T10:00:10+00:00",
        ),
    }

    site = domain_sites.site_from_latest_job(jobs, "playwright-dev-docs")

    assert site is not None
    assert site.start_url == "https://playwright.dev/docs/getting-started"
    assert site.allowed_host == "playwright.dev"
    assert site.allowed_path_prefix == "/docs/"


def test_site_from_topic_routes_uses_latest_updated_route():
    routes = {
        "playwright": mcp_state.TopicRouteRecord(
            topic="Playwright",
            topic_key="playwright",
            site_id="playwright-dev-docs",
            site_name="playwright.dev",
            start_url="https://playwright.dev/docs/intro",
            created_at="2026-07-12T10:00:00+00:00",
            updated_at="2026-07-12T10:00:00+00:00",
        ),
        "playwright-api": mcp_state.TopicRouteRecord(
            topic="Playwright API",
            topic_key="playwright api",
            site_id="playwright-dev-docs",
            site_name="playwright.dev",
            start_url="https://playwright.dev/docs/api/class-playwright",
            created_at="2026-07-12T10:00:00+00:00",
            updated_at="2026-07-13T10:00:00+00:00",
        ),
    }

    site = domain_sites.site_from_topic_routes(routes, "playwright-dev-docs")

    assert site is not None
    assert site.site_id == "playwright-dev-docs"
    assert site.allowed_host == "playwright.dev"
    assert site.allowed_path_prefix == "/docs/"


class _FakeCollection:
    def __init__(self, metadatas: list[dict[str, str]]):
        self.metadatas = metadatas

    def get(self, where: dict[str, str], include: list[str]):
        assert where == {"site_id": "playwright-dev-docs"}
        assert include == ["metadatas"]
        return {"metadatas": self.metadatas}


def test_site_from_indexed_metadata_picks_best_start_candidate():
    collection = _FakeCollection(
        metadatas=[
            {
                "site_id": "playwright-dev-docs",
                "site_name": "Playwright",
                "source_url": "https://playwright.dev/docs/api/class-page",
            },
            {
                "site_id": "playwright-dev-docs",
                "site_name": "Playwright",
                "source_url": "https://playwright.dev/docs/intro",
            },
        ]
    )

    site = mcp_runtime._site_from_indexed_metadata(collection, "playwright-dev-docs")

    assert site is not None
    assert site.site_name == "Playwright"
    assert site.start_url == "https://playwright.dev/docs/intro"
    assert site.allowed_host == "playwright.dev"
    assert site.allowed_path_prefix == "/docs/"


def test_site_from_url_scopes_sharepoint_site_collection():
    site = domain_sites.site_from_url("https://contoso.sharepoint.com/sites/engineering")

    assert site.allowed_host == "contoso.sharepoint.com"
    assert site.allowed_path_prefix == "/sites/engineering/"


def test_site_from_url_uses_root_scope_for_top_level_getting_started_entrypoint():
    site = domain_sites.site_from_url("https://docs.agentos.sh/getting-started")

    assert site.allowed_host == "docs.agentos.sh"
    assert site.allowed_path_prefix == "/"


def test_site_from_url_keeps_docs_scope_for_nested_getting_started_entrypoint():
    site = domain_sites.site_from_url("https://example.com/docs/getting-started")

    assert site.allowed_host == "example.com"
    assert site.allowed_path_prefix == "/docs/"


def test_site_from_url_scopes_sharepoint_folder_path():
    site = domain_sites.site_from_url(
        "https://contoso.sharepoint.com/sites/engineering/Shared%20Documents/Policies"
    )

    assert site.allowed_path_prefix == "/sites/engineering/Shared%20Documents/Policies/"


def test_site_from_url_scopes_sharepoint_file_to_parent_folder():
    site = domain_sites.site_from_url(
        "https://contoso.sharepoint.com/sites/engineering/Shared%20Documents/Policies/security-guide.pdf"
    )

    assert site.allowed_path_prefix == "/sites/engineering/Shared%20Documents/Policies/"


def test_site_from_url_scopes_sharepoint_allitems_query_to_requested_folder():
    site = domain_sites.site_from_url(
        "https://contoso.sharepoint.com/sites/engineering/Shared%20Documents/Forms/AllItems.aspx"
        "?id=%2Fsites%2Fengineering%2FShared%20Documents%2FPolicies"
    )

    assert site.allowed_path_prefix == "/sites/engineering/Shared%20Documents/Policies/"
