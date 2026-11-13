from __future__ import annotations

from ...domain.auth.browser import crawl_docs_with_playwright_session
from .scraper import crawl_docs

__all__ = ["crawl_docs", "crawl_docs_with_playwright_session"]
