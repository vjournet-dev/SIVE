from __future__ import annotations

from pathlib import Path

from sive.domain.core.sites import SiteDefinition
from sive.domain.ingest.pipeline import build_default_ingest_pipeline_orchestrator
from sive.infra.web.scraper import DocPage, DocSection


class _IncrementalResult:
    indexed_chunks = 7
    changed_pages = 3
    removed_pages = 1
    skipped_pages = 2


def _page(url: str) -> DocPage:
    return DocPage(
        site_id="site-a",
        site_name="Site A",
        url=url,
        title="Title",
        content="Content",
        content_hash="hash",
        sections=[DocSection(heading="Section", level=1, content="Body")],
    )


def _site() -> SiteDefinition:
    return SiteDefinition(
        site_id="site-a",
        site_name="Site A",
        start_url="https://docs.example.com/start",
        allowed_host="docs.example.com",
        allowed_path_prefix="/",
    )


def test_pipeline_orchestrator_incremental_path(tmp_path: Path):
    captured: dict[str, object] = {}

    def _load_pages(_request):
        return [_page("https://docs.example.com/1"), _page("https://docs.example.com/2"), _page("https://docs.example.com/3")]

    def _index_pages_incrementally(**kwargs):
        captured["incremental_kwargs"] = kwargs
        return _IncrementalResult()

    def _make_chunks(*_args, **_kwargs):
        raise AssertionError("make_chunks should not be called in incremental mode")

    def _index_chunks(**_kwargs):
        raise AssertionError("index_chunks should not be called in incremental mode")

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)

    orchestrator = build_default_ingest_pipeline_orchestrator(
        load_pages=_load_pages,
        index_pages_incrementally_func=_index_pages_incrementally,
        make_chunks_func=_make_chunks,
        index_chunks_func=_index_chunks,
        site_raw_docs_path_func=lambda site_id: raw_dir / f"{site_id}.jsonl",
        site_index_state_path_func=lambda site_id: raw_dir / f"{site_id}.state.json",
        chroma_dir="data/chroma",
    )

    result = orchestrator.run(
        _site(),
        incremental=True,
        max_pages=100,
        delay=0.2,
        crawl_progress_every=25,
        collection_name="docs",
        embedding_model_name="model",
        reset_collection=False,
        chunk_size=1200,
        overlap=200,
        progress_callback=None,
        auth_session=None,
    )

    assert result.indexed_chunks == 7
    assert result.changed_pages == 3
    assert result.removed_pages == 1
    assert result.skipped_pages == 2
    assert result.pages_scraped == 3
    assert (raw_dir / "site-a.jsonl").exists()
    assert captured["incremental_kwargs"]["collection_name"] == "docs"


def test_pipeline_orchestrator_non_incremental_path(tmp_path: Path):
    captured: dict[str, object] = {}

    def _load_pages(_request):
        return [_page("https://docs.example.com/1"), _page("https://docs.example.com/2")]

    def _index_pages_incrementally(**_kwargs):
        raise AssertionError("index_pages_incrementally should not be called in non-incremental mode")

    def _make_chunks(pages, *, chunk_size, overlap):
        captured["chunk_args"] = {"pages": pages, "chunk_size": chunk_size, "overlap": overlap}
        return ["c1", "c2", "c3"]

    def _index_chunks(**kwargs):
        captured["index_kwargs"] = kwargs
        progress_callback = kwargs.get("progress_callback")
        if callable(progress_callback):
            progress_callback(1, 3)
            progress_callback(3, 3)
        return 3

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)

    orchestrator = build_default_ingest_pipeline_orchestrator(
        load_pages=_load_pages,
        index_pages_incrementally_func=_index_pages_incrementally,
        make_chunks_func=_make_chunks,
        index_chunks_func=_index_chunks,
        site_raw_docs_path_func=lambda site_id: raw_dir / f"{site_id}.jsonl",
        site_index_state_path_func=lambda site_id: raw_dir / f"{site_id}.state.json",
        chroma_dir="data/chroma",
    )

    progress_events: list[dict[str, object]] = []
    result = orchestrator.run(
        _site(),
        incremental=False,
        max_pages=100,
        delay=0.2,
        crawl_progress_every=25,
        collection_name="docs",
        embedding_model_name="model",
        reset_collection=True,
        chunk_size=900,
        overlap=100,
        progress_callback=lambda event: progress_events.append(dict(event)),
        auth_session=None,
    )

    assert result.indexed_chunks == 3
    assert result.changed_pages == 2
    assert result.removed_pages == 0
    assert result.skipped_pages == 0
    assert captured["chunk_args"]["chunk_size"] == 900
    assert captured["chunk_args"]["overlap"] == 100
    assert captured["index_kwargs"]["reset_collection"] is True
    assert progress_events[-1]["phase"] == "index"
    assert any(event.get("index_total") == 3 for event in progress_events)
    assert any(event.get("index_done") == 3 for event in progress_events)
