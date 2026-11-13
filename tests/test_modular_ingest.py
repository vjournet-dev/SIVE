from __future__ import annotations

from sive.domain.core.sites import SiteDefinition
from sive.domain.ingest.contracts import IngestRequest
from sive.domain.ingest.orchestrator import build_default_ingest_orchestrator


def _request(site: SiteDefinition) -> IngestRequest:
    return IngestRequest(
        site=site,
        max_pages=100,
        delay=0.1,
        crawl_progress_every=25,
        progress_callback=None,
        auth_session=None,
    )


def test_default_orchestrator_registers_expected_method_plugins():
    orchestrator = build_default_ingest_orchestrator()

    assert orchestrator.method_registry.list_names() == [
        "local_source",
        "remote_document",
        "authenticated_scraping",
        "web_scrape",
    ]


def test_registry_resolves_local_source_for_existing_path(tmp_path):
    local_file = tmp_path / "sample.md"
    local_file.write_text("# title", encoding="utf-8")
    site = SiteDefinition(
        site_id="local-docs",
        site_name="Local Docs",
        start_url=str(local_file),
        allowed_host="",
        allowed_path_prefix="/",
    )

    orchestrator = build_default_ingest_orchestrator()
    plugin = orchestrator.method_registry.resolve(_request(site))

    assert plugin.name == "local_source"


def test_registry_resolves_remote_document_for_supported_remote_url():
    site = SiteDefinition(
        site_id="remote-doc",
        site_name="Remote Doc",
        start_url="https://example.com/docs/guide.pdf",
        allowed_host="example.com",
        allowed_path_prefix="/docs",
    )

    orchestrator = build_default_ingest_orchestrator()
    plugin = orchestrator.method_registry.resolve(_request(site))

    assert plugin.name == "remote_document"


def test_registry_resolves_web_scrape_for_regular_doc_site_url():
    site = SiteDefinition(
        site_id="web-doc",
        site_name="Web Doc",
        start_url="https://docs.example.com/getting-started/",
        allowed_host="docs.example.com",
        allowed_path_prefix="/",
    )

    orchestrator = build_default_ingest_orchestrator()
    plugin = orchestrator.method_registry.resolve(_request(site))

    assert plugin.name == "web_scrape"


def test_registry_resolves_authenticated_scraping_when_auth_session_is_present_for_web_route():
    site = SiteDefinition(
        site_id="protected-web-doc",
        site_name="Protected Web Doc",
        start_url="https://docs.example.com/private/",
        allowed_host="docs.example.com",
        allowed_path_prefix="/",
    )
    request = IngestRequest(
        site=site,
        max_pages=100,
        delay=0.1,
        crawl_progress_every=25,
        progress_callback=None,
        auth_session={"cookies": {"session": "abc"}, "headers": {}},
    )

    orchestrator = build_default_ingest_orchestrator()
    plugin = orchestrator.method_registry.resolve(request)

    assert plugin.name == "authenticated_scraping"
