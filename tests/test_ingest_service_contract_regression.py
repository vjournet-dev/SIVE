from __future__ import annotations

from dataclasses import dataclass

from sive.domain.core.sites import SiteDefinition
from sive.domain.ingest import service as ingest_service


def test_load_pages_for_site_web_route_forwards_parameters(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_crawl_docs(**kwargs):
        captured.update(kwargs)
        return ["web-page"]

    monkeypatch.setattr(ingest_service, "crawl_docs", _fake_crawl_docs)

    site = SiteDefinition(
        site_id="web-doc",
        site_name="Web Docs",
        start_url="https://docs.example.com/start/",
        allowed_host="docs.example.com",
        allowed_path_prefix="/",
        start_urls=("https://docs.example.com/start/", "https://docs.example.com/api/"),
        allowed_path_prefixes=("/start/", "/api/"),
    )
    auth_session = {"cookies": {"session": "abc"}, "headers": {}}

    pages = ingest_service.load_pages_for_site(
        site,
        max_pages=33,
        delay=0.4,
        crawl_progress_every=7,
        progress_callback=None,
        auth_session=auth_session,
    )

    assert pages == ["web-page"]
    assert captured["start_url"] == "https://docs.example.com/start/"
    assert captured["allowed_host"] == "docs.example.com"
    assert captured["allowed_path_prefix"] == "/"
    assert captured["start_urls"] == site.crawl_start_urls
    assert captured["allowed_path_prefixes"] == site.crawl_path_prefixes
    assert captured["site_id"] == "web-doc"
    assert captured["site_name"] == "Web Docs"
    assert captured["max_pages"] == 33
    assert captured["request_delay_seconds"] == 0.4
    assert captured["progress_every"] == 7
    assert captured["auth_session"] == auth_session


def test_load_pages_for_site_remote_route_emits_expected_crawl_progress(monkeypatch):
    def _fake_load_remote_pages(*args, **kwargs):
        return ["remote-1", "remote-2"]

    monkeypatch.setattr(ingest_service, "load_remote_pages", _fake_load_remote_pages)

    site = SiteDefinition(
        site_id="remote-pdf",
        site_name="manual.pdf",
        start_url="https://example.com/manual.pdf",
        allowed_host="example.com",
        allowed_path_prefix="/",
    )
    progress_events: list[dict[str, object]] = []

    pages = ingest_service.load_pages_for_site(
        site,
        max_pages=10,
        delay=0.0,
        crawl_progress_every=0,
        progress_callback=lambda event: progress_events.append(dict(event)),
        auth_session={"cookies": {"FedAuth": "x"}, "headers": {}},
    )

    assert pages == ["remote-1", "remote-2"]
    assert progress_events == [
        {
            "phase": "crawl",
            "visited": 2,
            "queued": 0,
            "pages_kept": 2,
        }
    ]


def test_load_pages_for_site_local_route_emits_expected_crawl_progress(monkeypatch, tmp_path):
    local_file = tmp_path / "readme.md"
    local_file.write_text("# title", encoding="utf-8")

    def _fake_load_local_pages(*args, **kwargs):
        return ["local-1"]

    monkeypatch.setattr(ingest_service, "load_local_pages", _fake_load_local_pages)

    site = SiteDefinition(
        site_id="local-doc",
        site_name="local",
        start_url=str(local_file),
        allowed_host="",
        allowed_path_prefix="/",
    )
    progress_events: list[dict[str, object]] = []

    pages = ingest_service.load_pages_for_site(
        site,
        max_pages=10,
        delay=0.0,
        crawl_progress_every=0,
        progress_callback=lambda event: progress_events.append(dict(event)),
    )

    assert pages == ["local-1"]
    assert progress_events == [
        {
            "phase": "crawl",
            "visited": 1,
            "queued": 0,
            "pages_kept": 1,
        }
    ]


def test_run_ingest_for_site_delegates_to_pipeline_orchestrator(monkeypatch):
    @dataclass(frozen=True)
    class _PipelineResult:
        pages_scraped: int
        indexed_chunks: int
        changed_pages: int
        removed_pages: int
        skipped_pages: int
        duration_seconds: float
        incremental: bool

    class _FakePipeline:
        def run(self, site: SiteDefinition, **kwargs):
            assert site.site_id == "site-1"
            assert kwargs["incremental"] is True
            return _PipelineResult(
                pages_scraped=10,
                indexed_chunks=25,
                changed_pages=4,
                removed_pages=1,
                skipped_pages=5,
                duration_seconds=2.5,
                incremental=True,
            )

    monkeypatch.setattr(ingest_service, "_default_ingest_pipeline_orchestrator", lambda: _FakePipeline())

    site = SiteDefinition(
        site_id="site-1",
        site_name="Site 1",
        start_url="https://docs.example.com",
        allowed_host="docs.example.com",
        allowed_path_prefix="/",
    )

    result = ingest_service.run_ingest_for_site(site, incremental=True)

    assert result.site_id == "site-1"
    assert result.pages_scraped == 10
    assert result.indexed_chunks == 25
    assert result.changed_pages == 4
    assert result.removed_pages == 1
    assert result.skipped_pages == 5
    assert result.duration_seconds == 2.5
    assert result.incremental is True
