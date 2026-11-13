from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from .session import (
    AuthSession,
    _get_sync_playwright,
    _inject_cookies_into_context,
    _looks_like_login_html,
    _looks_like_login_url,
)

_LOGGER = logging.getLogger(__name__)


def crawl_docs_with_playwright_session(
    *,
    start_url: str,
    allowed_host: str,
    allowed_path_prefix: str | Sequence[str],
    site_id: str,
    site_name: str,
    max_pages: int,
    timeout_seconds: float,
    progress_callback: Callable[[Any], None] | None,
    auth_session: AuthSession,
    normalize_url: Callable[[str], str],
    is_allowed_url: Callable[[str, str, str | Sequence[str]], bool],
    extract_page_content: Callable[..., Any],
    extract_links: Callable[[str, str], Iterable[str]],
    is_supported_remote_source_url: Callable[[str], bool] | None = None,
    load_remote_pages_for_url: Callable[[str], list[Any]] | None = None,
    get_sync_playwright: Callable[[], Any] = _get_sync_playwright,
    inject_cookies_into_context: Callable[[Any, dict[str, str], str], None] = _inject_cookies_into_context,
    start_urls: Sequence[str] | None = None,
) -> list[Any]:
    try:
        sync_playwright = get_sync_playwright()
    except RuntimeError:
        return []

    crawl_start_urls = tuple(
        dict.fromkeys(
            normalize_url(candidate)
            for candidate in (start_url, *(start_urls or ()))
            if candidate.strip()
        )
    )
    queue: deque[str] = deque(crawl_start_urls)
    visited: set[str] = set()
    queued: set[str] = set(crawl_start_urls)
    pages: list[Any] = []

    cookies = dict(auth_session.get("cookies") or {})
    headers = dict(auth_session.get("headers") or {})
    storage_state = auth_session.get("storage_state")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context_kwargs: dict[str, Any] = {}
            if isinstance(storage_state, dict) and storage_state:
                context_kwargs["storage_state"] = storage_state
            context = browser.new_context(**context_kwargs)
            if headers:
                context.set_extra_http_headers(headers)
            if cookies and not storage_state:
                inject_cookies_into_context(context, cookies, allowed_host)

            while queue and len(visited) < max_pages:
                url = queue.popleft()
                queued.discard(url)
                if url in visited or not is_allowed_url(url, allowed_host, allowed_path_prefix):
                    continue

                visited.add(url)

                if is_supported_remote_source_url and load_remote_pages_for_url and is_supported_remote_source_url(url):
                    try:
                        pages.extend(load_remote_pages_for_url(url))
                    except Exception:
                        _LOGGER.debug("Skipping remote source '%s' due to loader failure", url, exc_info=True)
                        continue

                    if progress_callback is not None:
                        progress_callback(
                            {
                                "phase": "crawl",
                                "visited": len(visited),
                                "queued": len(queue),
                                "pages_kept": len(pages),
                            }
                        )
                    continue

                page = context.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_seconds * 1000))
                    try:
                        page.wait_for_load_state("networkidle", timeout=min(5000, int(timeout_seconds * 1000)))
                    except Exception:
                        _LOGGER.debug("networkidle wait did not settle for '%s'", url, exc_info=True)

                    html = page.content()
                    effective_url = normalize_url(page.url or url)

                    if _looks_like_login_url(effective_url) and _looks_like_login_html(html):
                        continue

                    if not is_allowed_url(effective_url, allowed_host, allowed_path_prefix):
                        continue

                    page_data = extract_page_content(html, effective_url, site_id=site_id, site_name=site_name)
                    if page_data:
                        pages.append(page_data)

                    for link in extract_links(html, effective_url):
                        if link not in visited and link not in queued and is_allowed_url(
                            link,
                            allowed_host,
                            allowed_path_prefix,
                        ):
                            queue.append(link)
                            queued.add(link)

                    if progress_callback is not None:
                        progress_callback(
                            {
                                "phase": "crawl",
                                "visited": len(visited),
                                "queued": len(queue),
                                "pages_kept": len(pages),
                            }
                        )
                except Exception:
                    _LOGGER.debug("Skipping page '%s' due to browser extraction failure", url, exc_info=True)
                    continue
                finally:
                    page.close()

            return pages
        finally:
            browser.close()
