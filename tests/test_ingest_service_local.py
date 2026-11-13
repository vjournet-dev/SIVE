from sive.domain.core.sites import SiteDefinition
from sive.domain.index.indexing import IncrementalIndexResult
from sive.domain.ingest import service as ingest_service


def test_run_ingest_for_site_uses_local_loader_and_indexes_pages(monkeypatch, tmp_path):
    html_path = tmp_path / "manual.html"
    html_path.write_text(
        "<html><head><title>Manual</title></head><body><main><p>Local file content</p></main></body></html>",
        encoding="utf-8",
    )

    raw_output = tmp_path / "manual.jsonl"
    state_output = tmp_path / "manual.state.json"

    monkeypatch.setattr(ingest_service, "site_raw_docs_path", lambda _site_id: raw_output)
    monkeypatch.setattr(ingest_service, "site_index_state_path", lambda _site_id: state_output)

    def _fake_index_pages_incrementally(**kwargs):
        assert len(kwargs["pages"]) == 1
        assert kwargs["pages"][0].title == "Manual"
        return IncrementalIndexResult(
            indexed_chunks=3,
            changed_pages=1,
            removed_pages=0,
            skipped_pages=0,
        )

    monkeypatch.setattr(ingest_service, "index_pages_incrementally", _fake_index_pages_incrementally)

    site = SiteDefinition(
        site_id="local-manual",
        site_name="manual.html",
        start_url=str(html_path),
        allowed_host="local",
        allowed_path_prefix="/",
    )

    result = ingest_service.run_ingest_for_site(site, incremental=True, max_pages=10, delay=0.0)

    assert result.pages_scraped == 1
    assert result.indexed_chunks == 3
    assert result.changed_pages == 1
    assert raw_output.exists()