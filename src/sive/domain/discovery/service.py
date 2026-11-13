from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..core.sites import derive_allowed_path_prefix, score_start_path
from ..routing import normalize_topic

_LOGGER = logging.getLogger(__name__)

_QUERY_TEMPLATES = (
    "{topic} official documentation",
    "{topic} documentation",
    "{topic} getting started",
    "{topic} api reference",
)
_AGGREGATOR_HOSTS = (
    "medium.com",
    "dev.to",
    "stackoverflow.com",
    "geeksforgeeks.org",
    "tutorialspoint.com",
    "w3schools.com",
    "reddit.com",
)
_DOC_HOST_MARKERS = ("docs.", "developer.", "dev.", "readthedocs.io")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "api",
    "documentation",
    "docs",
    "for",
    "framework",
    "guide",
    "in",
    "library",
    "manual",
    "official",
    "reference",
    "sdk",
    "the",
    "with",
}


def _is_likely_doc_url(url: str) -> bool:
    lowered = url.lower()
    if any(token in lowered for token in ("docs", "documentation", "guide", "manual", "reference", "api")):
        return True
    parsed = urlparse(lowered)
    if parsed.netloc.startswith(("docs.", "developer.", "dev.")) or "readthedocs.io" in parsed.netloc:
        return True
    return "doc" in [segment for segment in parsed.path.split("/") if segment]


def _is_root_like_doc_path(path: str) -> bool:
    normalized = (path or "/").strip().rstrip("/").lower()
    return not normalized or normalized == "/" or normalized in {
        "/docs",
        "/documentation",
        "/api",
        "/guide",
        "/manual",
        "/reference",
    }


def _is_root_like_doc_url(url: str) -> bool:
    return _is_root_like_doc_path(urlparse(url).path)


def _score_start_path_normalized(path: str) -> float:
    return max(-1.0, min(1.0, score_start_path(path) / 120.0))


def _topic_terms(topic: str) -> set[str]:
    return {
        term
        for term in normalize_topic(topic).split()
        if len(term) >= 2 and term not in _STOP_WORDS
    }


def _term_overlap_score(text: str, terms: set[str]) -> float:
    if not terms:
        return 0.0
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered) / len(terms)


def _official_domain_score(host: str, title: str, snippet: str, topic_terms: set[str]) -> float:
    lowered_host = host.lower()
    if any(marker in lowered_host for marker in _AGGREGATOR_HOSTS):
        return -0.7
    labels = {label for label in re.split(r"[^a-z0-9]+", lowered_host) if label}
    topic_hits = sum(1 for term in topic_terms if term in labels)
    score = min(0.55, 0.25 + 0.15 * topic_hits) if topic_hits else 0.0
    if any(marker in lowered_host for marker in _DOC_HOST_MARKERS):
        score += 0.2
    title_snippet = f"{title} {snippet}".lower()
    if "official" in title_snippet and ("docs" in title_snippet or "documentation" in title_snippet):
        score += 0.2
    return min(1.0, max(-1.0, score))


def _score_candidate(
    *,
    topic_terms: set[str],
    target_url: str,
    refined_url: str,
    title: str,
    snippet: str,
) -> float:
    parsed_target = urlparse(target_url)
    parsed_refined = urlparse(refined_url)
    path_score = _score_start_path_normalized(parsed_refined.path)
    target_path_score = _score_start_path_normalized(parsed_target.path)
    relevance_text = f"{parsed_refined.netloc} {parsed_refined.path} {title} {snippet}".strip()
    return (
        0.45 * _official_domain_score(parsed_refined.netloc, title, snippet, topic_terms)
        + 0.3 * _term_overlap_score(relevance_text, topic_terms)
        + 0.2 * max(0.0, path_score)
        + (0.12 if path_score > target_path_score else 0.0)
    )


def refine_doc_start_url(
    url: str,
    *,
    http_client_factory: Callable[..., Any],
) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return url
    path = parsed.path or "/"
    if score_start_path(path) >= 90:
        return url

    allowed_prefix = derive_allowed_path_prefix(path)
    prefix_base = allowed_prefix.rstrip("/") or "/"
    candidates = {url.rstrip("/")}
    with http_client_factory(timeout=10.0, follow_redirects=True) as client:
        try:
            response = client.get(url)
            response.raise_for_status()
            if "text/html" in response.headers.get("content-type", ""):
                soup = BeautifulSoup(response.text, "lxml")
                for anchor in soup.find_all("a", href=True):
                    raw_href = anchor.get("href")
                    href = raw_href.strip() if isinstance(raw_href, str) else ""
                    if not href:
                        continue
                    absolute = urljoin(url, href)
                    parsed_absolute = urlparse(absolute)
                    candidate_path = (parsed_absolute.path or "/").rstrip("/") or "/"
                    if parsed_absolute.scheme not in {"http", "https"} or parsed_absolute.netloc != parsed.netloc:
                        continue
                    if prefix_base != "/" and not (
                        candidate_path == prefix_base or candidate_path.startswith(prefix_base + "/")
                    ):
                        continue
                    candidates.add(absolute.rstrip("/"))
        except Exception:
            _LOGGER.debug("Documentation entry page probe failed for '%s'.", url, exc_info=True)

        base_root = f"{parsed.scheme}://{parsed.netloc}"
        for suffix in ("intro", "introduction", "getting-started", "quickstart", "overview", "start"):
            probe_url = urljoin(base_root + "/", f"{prefix_base}/{suffix}".lstrip("/"))
            try:
                response = client.get(probe_url)
                response.raise_for_status()
                if "text/html" in response.headers.get("content-type", ""):
                    candidates.add(probe_url.rstrip("/"))
            except Exception:
                _LOGGER.debug("Documentation candidate probe failed for '%s'.", probe_url, exc_info=True)
                continue

    non_root = [candidate for candidate in candidates if not _is_root_like_doc_url(candidate)]
    return max(non_root or list(candidates), key=lambda candidate: score_start_path(urlparse(candidate).path))


def search_documentation_urls(
    topic: str,
    max_results: int,
    *,
    ddgs_factory: Callable[[], Any],
    refine_url: Callable[[str], str],
) -> list[dict[str, str]]:
    fetch_limit = min(50, max(max_results * 4, max_results))
    topic_terms = _topic_terms(topic)
    scored: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        with ddgs_factory() as ddgs:
            for query in (template.format(topic=topic) for template in _QUERY_TEMPLATES):
                for item in ddgs.text(query, max_results=fetch_limit):
                    if not isinstance(item, dict):
                        continue
                    target_url = str(item.get("href") or item.get("url") or "").strip()
                    parsed_target = urlparse(target_url)
                    if parsed_target.scheme not in {"http", "https"} or not parsed_target.netloc:
                        continue
                    refined_url = refine_url(target_url)
                    normalized = refined_url.rstrip("/")
                    if normalized in seen or _is_root_like_doc_url(normalized) or not _is_likely_doc_url(normalized):
                        continue
                    title = str(item.get("title") or "").strip()
                    snippet = str(item.get("body") or "").strip()
                    seen.add(normalized)
                    scored.append(
                        {
                            "title": title or snippet or normalized,
                            "url": refined_url,
                            "score": _score_candidate(
                                topic_terms=topic_terms,
                                target_url=target_url,
                                refined_url=refined_url,
                                title=title,
                                snippet=snippet,
                            ),
                        }
                    )
                high_confidence = sum(1 for entry in scored if float(entry["score"]) >= 0.55)
                if len(scored) >= max_results and high_confidence >= min(2, max_results):
                    break
    except Exception:  # noqa: BLE001 - provider failures return no suggestions
        return []

    ranked = sorted(
        scored,
        key=lambda entry: (float(entry["score"]), score_start_path(urlparse(str(entry["url"])).path)),
        reverse=True,
    )
    return [
        {"title": str(entry["title"]), "url": str(entry["url"])}
        for entry in ranked[:max_results]
    ]
