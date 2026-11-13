from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ...infra.web.scraper import DocPage
from .adapters import (
    AuthenticatedWebScrapeIngestMethod,
    LocalSourceIngestMethod,
    RemoteDocumentIngestMethod,
    WebScrapeIngestMethod,
)
from .contracts import IngestRequest
from .registry import IngestMethodRegistry


@dataclass
class IngestOrchestrator:
    method_registry: IngestMethodRegistry

    def load_pages(self, request: IngestRequest) -> list[DocPage]:
        plugin = self.method_registry.resolve(request)
        return plugin.load_pages(request)


def build_default_ingest_orchestrator(
    *,
    load_local_pages_func: Callable[..., list[DocPage]] | None = None,
    load_remote_pages_func: Callable[..., list[DocPage]] | None = None,
    crawl_docs_func: Callable[..., list[DocPage]] | None = None,
) -> IngestOrchestrator:
    registry = IngestMethodRegistry()
    local_method = LocalSourceIngestMethod() if load_local_pages_func is None else LocalSourceIngestMethod(load_local_pages_func)
    remote_method = (
        RemoteDocumentIngestMethod() if load_remote_pages_func is None else RemoteDocumentIngestMethod(load_remote_pages_func)
    )
    auth_web_method = (
        AuthenticatedWebScrapeIngestMethod()
        if crawl_docs_func is None
        else AuthenticatedWebScrapeIngestMethod(crawl_docs_func)
    )
    web_method = WebScrapeIngestMethod() if crawl_docs_func is None else WebScrapeIngestMethod(crawl_docs_func)
    registry.register(local_method)
    registry.register(remote_method)
    registry.register(auth_web_method)
    registry.register(web_method)
    return IngestOrchestrator(method_registry=registry)
