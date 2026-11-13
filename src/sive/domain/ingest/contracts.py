from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...domain.auth.session import AuthSession
from ...domain.core.sites import SiteDefinition
from ...infra.web.scraper import CrawlProgress, DocPage

ProgressCallback = Callable[[CrawlProgress], None] | None


@dataclass(frozen=True)
class IngestRequest:
	site: SiteDefinition
	max_pages: int
	delay: float
	crawl_progress_every: int
	progress_callback: ProgressCallback
	auth_session: AuthSession | None


class IngestMethodPlugin(Protocol):
	name: str

	def can_handle(self, request: IngestRequest) -> bool:
		...

	def load_pages(self, request: IngestRequest) -> list[DocPage]:
		...


__all__ = ["IngestMethodPlugin", "IngestRequest", "ProgressCallback"]
