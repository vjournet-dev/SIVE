from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import NotRequired, TypedDict
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup, Tag

from ...domain.auth.browser import crawl_docs_with_playwright_session
from ...domain.auth.session import (
    AuthConfig,
    AuthenticationRequiredError,
    AuthSession,
    _build_auth_session_from_config,
    _build_playwright_cookie_entries,
    _detect_login_page,
    _extract_allowed_host_cookies,
    _extract_storage_state,
    _get_sync_playwright,
    _has_strong_auth_cookie,
    _inject_cookies_into_context,
    _looks_like_login_html,
    _looks_like_login_url,
    _looks_like_protected_shell,
    capture_authenticated_cookies,
    capture_authenticated_session,
)

__all__ = [
    "AntiBotProtectionError",
    "AuthConfig",
    "AuthSession",
    "AuthenticationRequiredError",
    "CrawlProgress",
    "DocPage",
    "DocSection",
    "_build_auth_session_from_config",
    "_build_playwright_cookie_entries",
    "_crawl_docs_with_playwright_session",
    "_detect_login_page",
    "_extract_allowed_host_cookies",
    "_extract_storage_state",
    "_get_sync_playwright",
    "_has_strong_auth_cookie",
    "_inject_cookies_into_context",
    "_looks_like_login_html",
    "_looks_like_login_url",
    "_looks_like_protected_shell",
    "capture_authenticated_cookies",
    "capture_authenticated_session",
    "crawl_docs",
    "extract_links",
    "extract_page_content",
    "extract_sections",
    "hash_content",
    "is_allowed_url",
    "load_pages_jsonl",
    "normalize_url",
    "save_pages_jsonl",
]


_LOGGER = logging.getLogger(__name__)
_BROWSER_BLOCK_STATUS_CODES = {403, 429}
_BROWSER_BLOCK_MARKERS = (
    "just a moment",
    "attention required",
    "cf-browser-verification",
    "cloudflare",
)


class AntiBotProtectionError(RuntimeError):
    pass


@dataclass
class DocSection:
    heading: str
    level: int
    content: str


@dataclass
class DocPage:
    site_id: str
    site_name: str
    url: str
    title: str
    content: str
    content_hash: str
    sections: list[DocSection]


class CrawlProgress(TypedDict):
    phase: str
    visited: int
    queued: int
    pages_kept: int
    index_done: NotRequired[int]
    index_total: NotRequired[int]


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    cleaned = parsed._replace(fragment="", query="")
    return urlunparse(cleaned)


def _normalize_discovered_link_url(url: str) -> str:
    parsed = urlparse(url)
    cleaned = parsed._replace(fragment="")

    query = parse_qs(parsed.query)
    preserve_query_keys = {"id", "file", "SourceUrl", "sourceurl", "sourcedoc"}
    if any(query.get(key) for key in preserve_query_keys):
        return urlunparse(cleaned)

    cleaned = cleaned._replace(query="")
    return urlunparse(cleaned)


def _canonicalize_sharepoint_view_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 4:
        return normalize_url(url)

    if parts[-1].lower() != "allitems.aspx" or parts[-2].lower() != "forms":
        return normalize_url(url)

    query = parse_qs(parsed.query)
    for key in ("id", "RootFolder"):
        for raw_value in query.get(key, []):
            decoded = unquote(str(raw_value or "")).strip()
            if not decoded.startswith("/"):
                continue
            canonical_path = "/" + "/".join(part for part in decoded.split("/") if part)
            if canonical_path == "/":
                continue
            return urlunparse(parsed._replace(path=quote(canonical_path, safe="/"), query="", fragment=""))

    canonical_path = "/" + "/".join(parts[:-2])
    return urlunparse(parsed._replace(path=quote(canonical_path, safe="/"), query="", fragment=""))


def _normalize_allowed_path_prefix(prefix: str) -> str:
    normalized = (prefix or "/").strip()
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    normalized = "/" + normalized.strip("/") if normalized != "/" else "/"
    return normalized


def is_allowed_url(url: str, allowed_host: str, allowed_path_prefix: str | Sequence[str]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc != allowed_host:
        return False

    path = parsed.path or "/"
    prefixes = (allowed_path_prefix,) if isinstance(allowed_path_prefix, str) else allowed_path_prefix
    for prefix in prefixes:
        normalized_prefix = _normalize_allowed_path_prefix(prefix)
        if normalized_prefix == "/":
            return True

        # Accept both the section root (/docs) and descendants (/docs/...).
        if path == normalized_prefix or path.startswith((normalized_prefix + "/", normalized_prefix + ".")):
            return True
    return False


def extract_links(html: str, base_url: str) -> Iterable[str]:
    soup = BeautifulSoup(html, "lxml")
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        if not isinstance(href, str) or not href:
            continue
        yield _normalize_discovered_link_url(urljoin(base_url, href))


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _requires_browser_fetch(response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type:
        return False

    if response.status_code in _BROWSER_BLOCK_STATUS_CODES:
        return True

    snippet = response.text[:2000].lower() if response.text else ""
    return any(marker in snippet for marker in _BROWSER_BLOCK_MARKERS)


def _looks_like_browser_block_html(html: str) -> bool:
    snippet = html[:4000].lower()
    return any(marker in snippet for marker in _BROWSER_BLOCK_MARKERS)


def _fetch_html_with_playwright(url: str, timeout_seconds: float) -> tuple[str, str] | None:
    try:
        sync_playwright = _get_sync_playwright()
    except RuntimeError:
        _LOGGER.debug(
            "Playwright browser fallback requested for '%s', but the Python package is not installed.",
            url,
        )
        return None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_seconds * 1000))
                html = page.content()
                if _looks_like_browser_block_html(html):
                    page.wait_for_timeout(min(5000, int(timeout_seconds * 1000)))
                    html = page.content()
                if _looks_like_browser_block_html(html):
                    _LOGGER.debug(
                        "Playwright browser fallback still received a bot-protection page for '%s'.",
                        url,
                    )
                    return None
                final_url = _canonicalize_sharepoint_view_url(page.url or url)
                if not html.strip():
                    return None
                return html, final_url
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001 - browser fallback should degrade gracefully on any Playwright failure
        _LOGGER.debug("Playwright browser fallback failed for '%s': %s", url, exc)
        return None


def _crawl_docs_with_playwright_session(
    *,
    start_url: str,
    allowed_host: str,
    allowed_path_prefix: str | Sequence[str],
    site_id: str,
    site_name: str,
    max_pages: int,
    timeout_seconds: float,
    progress_callback: Callable[[CrawlProgress], None] | None,
    auth_session: AuthSession,
    start_urls: Sequence[str] | None = None,
) -> list[DocPage]:
    def _load_remote_pages_for_url(url: str) -> list[DocPage]:
        from ...domain.parse.loader import load_remote_pages

        return load_remote_pages(
            url,
            site_id=site_id,
            site_name=site_name,
            auth_session=auth_session,
            timeout_seconds=timeout_seconds,
        )

    pages = crawl_docs_with_playwright_session(
        start_url=start_url,
        start_urls=start_urls,
        allowed_host=allowed_host,
        allowed_path_prefix=allowed_path_prefix,
        site_id=site_id,
        site_name=site_name,
        max_pages=max_pages,
        timeout_seconds=timeout_seconds,
        progress_callback=progress_callback,
        auth_session=auth_session,
        normalize_url=_canonicalize_sharepoint_view_url,
        is_allowed_url=is_allowed_url,
        extract_page_content=extract_page_content,
        extract_links=extract_links,
        is_supported_remote_source_url=_is_supported_remote_source_url,
        load_remote_pages_for_url=_load_remote_pages_for_url,
        get_sync_playwright=_get_sync_playwright,
        inject_cookies_into_context=_inject_cookies_into_context,
    )
    return pages


def _is_supported_remote_source_url(url: str) -> bool:
    from ...domain.parse.loader import is_supported_remote_source_url

    return is_supported_remote_source_url(url)


def _load_remote_pages_for_crawl(
    url: str,
    *,
    site_id: str,
    site_name: str,
    auth_session: AuthSession | None,
    timeout_seconds: float,
) -> list[DocPage]:
    from ...domain.parse.loader import load_remote_pages

    return load_remote_pages(
        url,
        site_id=site_id,
        site_name=site_name,
        auth_session=auth_session,
        timeout_seconds=timeout_seconds,
    )


def _is_heading(tag: Tag) -> bool:
    return tag.name in {"h1", "h2", "h3", "h4", "h5", "h6"}


def extract_sections(main: Tag) -> list[DocSection]:
    sections: list[DocSection] = []
    current_heading = "Introduction"
    current_level = 1
    current_lines: list[str] = []

    for element in main.descendants:
        if not isinstance(element, Tag):
            continue

        if _is_heading(element):
            text = element.get_text(" ", strip=True)
            if current_lines:
                section_text = "\n".join(current_lines).strip()
                if section_text:
                    sections.append(DocSection(heading=current_heading, level=current_level, content=section_text))
            current_heading = text or current_heading
            current_level = int(element.name[1])
            current_lines = []
            continue

        if element.name not in {"p", "li", "pre", "code", "blockquote", "table"}:
            continue

        text = element.get_text(" ", strip=True)
        if text:
            current_lines.append(text)

    if current_lines:
        section_text = "\n".join(current_lines).strip()
        if section_text:
            sections.append(DocSection(heading=current_heading, level=current_level, content=section_text))

    return sections


def extract_page_content(html: str, url: str, site_id: str, site_name: str) -> DocPage | None:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title = (soup.title.string or "").strip() if soup.title else ""

    # Docusaurus pages usually contain the primary article in <main>.
    main = soup.find("main") or soup.find("article") or soup.body
    if not main:
        return None

    for selector in ["nav", "footer", "aside"]:
        for tag in main.select(selector):
            tag.decompose()

    text = "\n".join(line.strip() for line in main.get_text("\n").splitlines() if line.strip())
    if not text:
        return None

    sections = extract_sections(main)

    return DocPage(
        site_id=site_id,
        site_name=site_name,
        url=url,
        title=title,
        content=text,
        content_hash=hash_content(text),
        sections=sections,
    )


def crawl_docs(
    start_url: str,
    allowed_host: str,
    allowed_path_prefix: str | Sequence[str],
    site_id: str,
    site_name: str,
    max_pages: int = 1200,
    request_delay_seconds: float = 0.2,
    timeout_seconds: float = 20.0,
    progress_every: int = 25,
    progress_callback: Callable[[CrawlProgress], None] | None = None,
    auth_session: AuthSession | None = None,
    start_urls: Sequence[str] | None = None,
    allowed_path_prefixes: Sequence[str] | None = None,
) -> list[DocPage]:
    seed_url = normalize_url(start_url)
    crawl_start_urls = tuple(
        dict.fromkeys(
            normalize_url(candidate)
            for candidate in (start_url, *(start_urls or ()))
            if candidate.strip()
        )
    )
    crawl_path_prefixes = tuple(
        dict.fromkeys(
            (
                *((allowed_path_prefix,) if isinstance(allowed_path_prefix, str) else allowed_path_prefix),
                *(allowed_path_prefixes or ()),
            )
        )
    )
    queue: deque[str] = deque(crawl_start_urls)
    visited: set[str] = set()
    queued: set[str] = set(crawl_start_urls)
    pages: list[DocPage] = []
    attempted = 0
    blocked_by_bot_protection = False
    saw_soft_auth_block = False
    auth_headers = dict((auth_session or {}).get("headers") or {})
    auth_cookies = dict((auth_session or {}).get("cookies") or {})

    if auth_session and (auth_cookies or auth_headers):
        browser_pages = _crawl_docs_with_playwright_session(
            start_url=start_url,
            start_urls=crawl_start_urls,
            allowed_host=allowed_host,
            allowed_path_prefix=crawl_path_prefixes,
            site_id=site_id,
            site_name=site_name,
            max_pages=max_pages,
            timeout_seconds=timeout_seconds,
            progress_callback=progress_callback,
            auth_session=auth_session,
        )
        if browser_pages:
            return browser_pages

    with httpx.Client(timeout=timeout_seconds, follow_redirects=True, cookies=auth_cookies, headers=auth_headers) as client:
        while queue and len(visited) < max_pages:
            url = queue.popleft()
            queued.discard(url)
            if url in visited or not is_allowed_url(url, allowed_host, crawl_path_prefixes):
                continue

            visited.add(url)

            if _is_supported_remote_source_url(url):
                try:
                    pages.extend(
                        _load_remote_pages_for_crawl(
                            url,
                            site_id=site_id,
                            site_name=site_name,
                            auth_session=auth_session,
                            timeout_seconds=timeout_seconds,
                        )
                    )
                except Exception:
                    _LOGGER.debug("Skipping remote source '%s' due to loader failure", url, exc_info=True)
                    continue

                if progress_callback is not None:
                    remote_progress: CrawlProgress = {
                        "phase": "crawl",
                        "visited": len(visited),
                        "queued": len(queue),
                        "pages_kept": len(pages),
                    }
                    progress_callback(remote_progress)

                time.sleep(request_delay_seconds)
                continue

            attempted += 1
            if progress_every > 0 and attempted % progress_every == 0:
                print(
                    f"Crawl progress: {len(pages)} pages kept, {len(visited)} URLs visited, {len(queue)} queued"
                )

            try:
                response = client.get(url)
            except httpx.HTTPError:
                continue

            login_url = _detect_login_page(response)
            if login_url:
                raise AuthenticationRequiredError(
                    "Authentication is required to access this documentation site.",
                    login_url=login_url,
                )

            if _requires_browser_fetch(response):
                blocked_by_bot_protection = True
                browser_result = _fetch_html_with_playwright(url, timeout_seconds=timeout_seconds)
                if browser_result is None:
                    continue
                html, effective_url = browser_result
                if _looks_like_login_url(effective_url) and _looks_like_login_html(html):
                    raise AuthenticationRequiredError(
                        "Authentication is required to access this documentation site.",
                        login_url=effective_url,
                    )
                if _looks_like_protected_shell(html):
                    saw_soft_auth_block = True
                    raise AuthenticationRequiredError(
                        "Authentication is required to access this protected documentation site.",
                        login_url=effective_url,
                    )
            else:
                try:
                    response.raise_for_status()
                except httpx.HTTPError:
                    continue

                if "text/html" not in response.headers.get("content-type", ""):
                    continue

                html = response.text
                effective_url = _canonicalize_sharepoint_view_url(str(response.url))

                if _looks_like_protected_shell(html):
                    saw_soft_auth_block = True
                    raise AuthenticationRequiredError(
                        "Authentication is required to access this protected documentation site.",
                        login_url=effective_url,
                    )

            if not is_allowed_url(effective_url, allowed_host, crawl_path_prefixes):
                continue

            page = extract_page_content(html, effective_url, site_id=site_id, site_name=site_name)
            if page:
                pages.append(page)

            for link in extract_links(html, effective_url):
                if (
                    link not in visited
                    and link not in queued
                    and is_allowed_url(link, allowed_host, crawl_path_prefixes)
                ):
                    queue.append(link)
                    queued.add(link)

            if progress_callback is not None:
                progress: CrawlProgress = {
                    "phase": "crawl",
                    "visited": len(visited),
                    "queued": len(queue),
                    "pages_kept": len(pages),
                }
                progress_callback(progress)

            time.sleep(request_delay_seconds)

    if not pages and blocked_by_bot_protection:
        raise AntiBotProtectionError(
            "The target site appears to be protected by anti-bot or challenge pages. "
            "No documentation pages could be scraped automatically."
        )

    if not pages and (auth_session is None or not auth_cookies):
        reason = (
            "The target protected site did not expose readable documentation pages without authentication."
            if saw_soft_auth_block
            else "The target protected site returned no readable documentation pages."
        )
        raise AuthenticationRequiredError(
            f"{reason} Use authenticate_ingest_job(job_id) to continue with an interactive login.",
            login_url=seed_url,
        )

    return pages


def save_pages_jsonl(pages: list[DocPage], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for page in pages:
            handle.write(json.dumps(asdict(page), ensure_ascii=False) + "\n")


def load_pages_jsonl(input_path: Path) -> list[DocPage]:
    pages: list[DocPage] = []
    with input_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            data = json.loads(line)
            sections = [DocSection(**section) for section in data.get("sections", [])]
            content = data["content"]
            pages.append(
                DocPage(
                    site_id=data.get("site_id", "default"),
                    site_name=data.get("site_name", data.get("site_id", "Default")),
                    url=data["url"],
                    title=data.get("title", ""),
                    content=content,
                    content_hash=data.get("content_hash", hash_content(content)),
                    sections=sections,
                )
            )
    return pages
