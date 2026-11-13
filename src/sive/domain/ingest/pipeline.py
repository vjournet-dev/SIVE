from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...domain.core.sites import SiteDefinition
from ...infra.web.scraper import AuthSession, CrawlProgress, DocPage, save_pages_jsonl
from .contracts import IngestRequest

ProgressCallback = Callable[[CrawlProgress], None] | None


@dataclass(frozen=True)
class IngestPipelineResult:
    pages_scraped: int
    indexed_chunks: int
    changed_pages: int
    removed_pages: int
    skipped_pages: int
    duration_seconds: float
    incremental: bool


@dataclass
class IngestPipelineOrchestrator:
    load_pages: Callable[[IngestRequest], list[DocPage]]
    index_pages_incrementally_func: Callable[..., Any]
    make_chunks_func: Callable[..., list[Any]]
    index_chunks_func: Callable[..., int]
    site_raw_docs_path_func: Callable[[str], Path]
    site_index_state_path_func: Callable[[str], Path]
    chroma_dir: str

    def run(
        self,
        site: SiteDefinition,
        *,
        incremental: bool,
        max_pages: int,
        delay: float,
        crawl_progress_every: int,
        collection_name: str,
        embedding_model_name: str,
        reset_collection: bool,
        chunk_size: int,
        overlap: int,
        progress_callback: ProgressCallback,
        auth_session: AuthSession | None,
    ) -> IngestPipelineResult:
        started_at = time.perf_counter()
        request = IngestRequest(
            site=site,
            max_pages=max_pages,
            delay=delay,
            crawl_progress_every=crawl_progress_every,
            progress_callback=progress_callback,
            auth_session=auth_session,
        )
        pages = self.load_pages(request)

        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "index",
                    "visited": len(pages),
                    "queued": 0,
                    "pages_kept": len(pages),
                    "index_done": 0,
                    "index_total": 0,
                }
            )

        save_pages_jsonl(pages, self.site_raw_docs_path_func(site.site_id))

        def _on_index_progress(index_done: int, index_total: int) -> None:
            if progress_callback is None:
                return
            progress_callback(
                {
                    "phase": "index",
                    "visited": len(pages),
                    "queued": 0,
                    "pages_kept": len(pages),
                    "index_done": max(0, int(index_done)),
                    "index_total": max(0, int(index_total)),
                }
            )

        if incremental:
            indexing_result = self.index_pages_incrementally_func(
                pages=pages,
                chroma_dir=self.chroma_dir,
                collection_name=collection_name,
                state_path=self.site_index_state_path_func(site.site_id),
                reset_collection=reset_collection,
                embedding_model_name=embedding_model_name,
                chunk_size=chunk_size,
                overlap=overlap,
                progress_callback=_on_index_progress,
            )
            indexed_chunks = int(indexing_result.indexed_chunks)
            changed_pages = int(indexing_result.changed_pages)
            removed_pages = int(indexing_result.removed_pages)
            skipped_pages = int(indexing_result.skipped_pages)
        else:
            chunks = self.make_chunks_func(pages, chunk_size=chunk_size, overlap=overlap)
            indexed_chunks = self.index_chunks_func(
                chunks=chunks,
                chroma_dir=self.chroma_dir,
                collection_name=collection_name,
                reset_collection=reset_collection,
                embedding_model_name=embedding_model_name,
                progress_callback=_on_index_progress,
            )
            changed_pages = len(pages)
            removed_pages = 0
            skipped_pages = 0

        return IngestPipelineResult(
            pages_scraped=len(pages),
            indexed_chunks=indexed_chunks,
            changed_pages=changed_pages,
            removed_pages=removed_pages,
            skipped_pages=skipped_pages,
            duration_seconds=time.perf_counter() - started_at,
            incremental=incremental,
        )


def build_default_ingest_pipeline_orchestrator(
    *,
    load_pages: Callable[[IngestRequest], list[DocPage]],
    index_pages_incrementally_func: Callable[..., Any],
    make_chunks_func: Callable[..., list[Any]],
    index_chunks_func: Callable[..., int],
    site_raw_docs_path_func: Callable[[str], Path],
    site_index_state_path_func: Callable[[str], Path],
    chroma_dir: str,
) -> IngestPipelineOrchestrator:
    return IngestPipelineOrchestrator(
        load_pages=load_pages,
        index_pages_incrementally_func=index_pages_incrementally_func,
        make_chunks_func=make_chunks_func,
        index_chunks_func=index_chunks_func,
        site_raw_docs_path_func=site_raw_docs_path_func,
        site_index_state_path_func=site_index_state_path_func,
        chroma_dir=chroma_dir,
    )