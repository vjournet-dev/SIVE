"""Web infrastructure facade."""

from __future__ import annotations

from .adapters import crawl_docs, crawl_docs_with_playwright_session

__all__ = ["crawl_docs", "crawl_docs_with_playwright_session"]
