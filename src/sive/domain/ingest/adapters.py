from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ...domain.parse.loader import is_supported_remote_source_url, load_local_pages, load_remote_pages
from ...infra.web.scraper import DocPage, crawl_docs
from .contracts import IngestMethodPlugin, IngestRequest


def _is_local_source(start_value: str) -> bool:
    if not start_value.strip():
        return False
    return Path(start_value).expanduser().exists()


def _is_remote_document_source(start_value: str) -> bool:
    if not start_value.strip():
        return False
    return is_supported_remote_source_url(start_value)


class LocalSourceIngestMethod(IngestMethodPlugin):
    name = "local_source"

    def __init__(self, load_local_pages_func: Callable[..., list[DocPage]] = load_local_pages) -> None:
        self._load_local_pages = load_local_pages_func

    def can_handle(self, request: IngestRequest) -> bool:
        return _is_local_source(request.site.start_url)

    def load_pages(self, request: IngestRequest):
        pages = self._load_local_pages(
            request.site.start_url,
            site_id=request.site.site_id,
            site_name=request.site.site_name,
        )
        if request.progress_callback is not None:
            request.progress_callback(
                {
                    "phase": "crawl",
                    "visited": len(pages),
                    "queued": 0,
                    "pages_kept": len(pages),
                }
            )
        return pages


class RemoteDocumentIngestMethod(IngestMethodPlugin):
    name = "remote_document"

    def __init__(self, load_remote_pages_func: Callable[..., list[DocPage]] = load_remote_pages) -> None:
        self._load_remote_pages = load_remote_pages_func

    def can_handle(self, request: IngestRequest) -> bool:
        return _is_remote_document_source(request.site.start_url)

    def load_pages(self, request: IngestRequest):
        pages = self._load_remote_pages(
            request.site.start_url,
            site_id=request.site.site_id,
            site_name=request.site.site_name,
            auth_session=request.auth_session,
        )
        if request.progress_callback is not None:
            request.progress_callback(
                {
                    "phase": "crawl",
                    "visited": len(pages),
                    "queued": 0,
                    "pages_kept": len(pages),
                }
            )
        return pages


class WebScrapeIngestMethod(IngestMethodPlugin):
    name = "web_scrape"

    def __init__(self, crawl_docs_func: Callable[..., list[DocPage]] = crawl_docs) -> None:
        self._crawl_docs = crawl_docs_func

    def can_handle(self, request: IngestRequest) -> bool:
        # Fallback method when local and direct-remote sources do not apply.
        return True

    def load_pages(self, request: IngestRequest):
        site = request.site
        return self._crawl_docs(
            start_url=site.start_url,
            allowed_host=site.allowed_host,
            allowed_path_prefix=site.allowed_path_prefix,
            start_urls=site.crawl_start_urls,
            allowed_path_prefixes=site.crawl_path_prefixes,
            site_id=site.site_id,
            site_name=site.site_name,
            max_pages=request.max_pages,
            request_delay_seconds=request.delay,
            progress_every=request.crawl_progress_every,
            progress_callback=request.progress_callback,
            auth_session=request.auth_session,
        )


class AuthenticatedWebScrapeIngestMethod(IngestMethodPlugin):
    name = "authenticated_scraping"

    def __init__(self, crawl_docs_func: Callable[..., list[DocPage]] = crawl_docs) -> None:
        self._crawl_docs = crawl_docs_func

    def can_handle(self, request: IngestRequest) -> bool:
        # Distinct method for protected web routes when an auth session is available.
        if request.auth_session is None:
            return False
        start_url = request.site.start_url
        return not _is_local_source(start_url) and not _is_remote_document_source(start_url)

    def load_pages(self, request: IngestRequest):
        site = request.site
        return self._crawl_docs(
            start_url=site.start_url,
            allowed_host=site.allowed_host,
            allowed_path_prefix=site.allowed_path_prefix,
            start_urls=site.crawl_start_urls,
            allowed_path_prefixes=site.crawl_path_prefixes,
            site_id=site.site_id,
            site_name=site.site_name,
            max_pages=request.max_pages,
            request_delay_seconds=request.delay,
            progress_every=request.crawl_progress_every,
            progress_callback=request.progress_callback,
            auth_session=request.auth_session,
        )
