from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class RankedSearchResult:
    document: str
    metadata: dict[str, Any]
    distance: float
    semantic_score: float
    rank_score: float


def format_search_results(docs: list[str], metas: list[dict[str, Any]], distances: list[float]) -> str:
    lines: list[str] = []
    for idx, (doc, meta, distance) in enumerate(zip(docs, metas, distances), start=1):
        source_url = meta.get("source_url", "") if isinstance(meta, dict) else ""
        title = meta.get("title", "") if isinstance(meta, dict) else ""
        site_id = meta.get("site_id", "") if isinstance(meta, dict) else ""
        site_name = meta.get("site_name", site_id) if isinstance(meta, dict) else ""
        section_heading = meta.get("section_heading", "") if isinstance(meta, dict) else ""
        page_number = meta.get("page_number") if isinstance(meta, dict) else None
        source_kind = str(meta.get("source_kind", "")) if isinstance(meta, dict) else ""
        score = 1.0 / (1.0 + float(distance))
        snippet = doc[:1200].strip()
        if len(doc) > len(snippet):
            snippet = f"{snippet}\n[...truncated...]"

        section_type = "section"
        lowered_heading = section_heading.lower()
        if "summary" in lowered_heading:
            section_type = "summary"
        elif "columns" in lowered_heading:
            section_type = "columns"
        elif "row " in lowered_heading:
            section_type = "row"
        elif isinstance(page_number, int):
            section_type = "page"

        section_line = f"Section: {section_heading}"
        if isinstance(page_number, int):
            section_line = f"Section: {section_heading} (page {page_number})"

        lines.append(
            f"Result {idx}\n"
            f"Site: {site_name} ({site_id})\n"
            f"Title: {title}\n"
            f"Source Kind: {source_kind or 'unknown'}\n"
            f"Section Type: {section_type}\n"
            f"{section_line}\n"
            f"Source: {source_url}\n"
            f"Relevance: {score:.4f}\n"
            f"Excerpt:\n{snippet}\n"
        )
    return "\n---\n".join(lines)


def format_ranked_search_results(results: list[RankedSearchResult]) -> str:
    lines: list[str] = []
    for index, result in enumerate(results, start=1):
        meta = result.metadata
        source_url = str(meta.get("source_url", ""))
        title = str(meta.get("title", ""))
        site_id = str(meta.get("site_id", ""))
        site_name = str(meta.get("site_name", site_id))
        section_heading = str(meta.get("section_heading", ""))
        page_number = meta.get("page_number")
        source_kind = str(meta.get("source_kind", ""))
        snippet = result.document[:1200].strip()
        if len(result.document) > len(snippet):
            snippet = f"{snippet}\n[...truncated...]"

        section_type = "section"
        lowered_heading = section_heading.lower()
        if "summary" in lowered_heading:
            section_type = "summary"
        elif "columns" in lowered_heading:
            section_type = "columns"
        elif "row " in lowered_heading:
            section_type = "row"
        elif isinstance(page_number, int):
            section_type = "page"

        section_line = f"Section: {section_heading}"
        if isinstance(page_number, int):
            section_line = f"Section: {section_heading} (page {page_number})"

        lines.append(
            f"Result {index}\n"
            f"Site: {site_name} ({site_id})\n"
            f"Title: {title}\n"
            f"Source Kind: {source_kind or 'unknown'}\n"
            f"Section Type: {section_type}\n"
            f"{section_line}\n"
            f"Source: {source_url}\n"
            f"Semantic Relevance: {result.semantic_score:.4f}\n"
            f"Rank Score: {result.rank_score:.4f}\n"
            f"Excerpt:\n{snippet}\n"
        )
    return "\n---\n".join(lines)


def _query_terms(query: str, normalize_topic: Callable[[str], str]) -> set[str]:
    normalized = normalize_topic(query)
    return {term for term in normalized.split() if len(term) >= 2}


def _term_overlap_score(text: str, query_terms: set[str], normalize_topic: Callable[[str], str]) -> float:
    normalized = normalize_topic(text)
    if not normalized or not query_terms:
        return 0.0
    matched = 0
    for term in query_terms:
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", normalized):
            matched += 1
    return matched / max(1, len(query_terms))


class _RerankBoostStrategy(Protocol):
    @property
    def name(self) -> str:
        ...

    def additional_boost(self, meta: dict[str, Any], query_terms: set[str]) -> float:
        ...


class _GenericRerankStrategy:
    @property
    def name(self) -> str:
        return "generic"

    def additional_boost(self, meta: dict[str, Any], query_terms: set[str]) -> float:
        return 0.0


class _NarrativeRerankStrategy:
    @property
    def name(self) -> str:
        return "narrative"

    def additional_boost(self, meta: dict[str, Any], query_terms: set[str]) -> float:
        boost = 0.0

        source_kind = str(meta.get("source_kind", "")).lower()
        json_terms = {"json", "field", "fields", "property", "properties", "schema", "config"}
        doc_terms = {"page", "chapter", "section", "document"}

        if source_kind == "json" and query_terms & json_terms:
            boost += 0.12

        if source_kind == "docx" and query_terms & doc_terms:
            boost += 0.05

        if source_kind == "markdown":
            boost += _markdown_content_boost(meta, query_terms)

        return boost


class _TabularRerankStrategy:
    @property
    def name(self) -> str:
        return "tabular"

    def additional_boost(self, meta: dict[str, Any], query_terms: set[str]) -> float:
        tabular_terms = {
            "csv",
            "xlsx",
            "excel",
            "spreadsheet",
            "sheet",
            "table",
            "row",
            "rows",
            "column",
            "columns",
        }

        boost = 0.12 if query_terms & tabular_terms else 0.0
        boost += _summary_section_boost(meta, query_terms)
        return boost


class _PdfRerankStrategy:
    @property
    def name(self) -> str:
        return "pdf"

    def additional_boost(self, meta: dict[str, Any], query_terms: set[str]) -> float:
        doc_terms = {"page", "chapter", "section", "document"}
        return 0.05 if query_terms & doc_terms else 0.0


_DEFAULT_RERANK_STRATEGY: _RerankBoostStrategy = _GenericRerankStrategy()
_RERANK_STRATEGIES_BY_SOURCE_KIND: dict[str, _RerankBoostStrategy] = {
    "markdown": _NarrativeRerankStrategy(),
    "html": _NarrativeRerankStrategy(),
    "docx": _NarrativeRerankStrategy(),
    "json": _NarrativeRerankStrategy(),
    "csv": _TabularRerankStrategy(),
    "xlsx": _TabularRerankStrategy(),
    "pdf": _PdfRerankStrategy(),
}


def _resolve_rerank_strategy(source_kind: str) -> _RerankBoostStrategy:
    key = source_kind.strip().lower()
    return _RERANK_STRATEGIES_BY_SOURCE_KIND.get(key, _DEFAULT_RERANK_STRATEGY)


def _summary_section_boost(meta: dict[str, Any], query_terms: set[str]) -> float:
    section_heading = str(meta.get("section_heading", "")).lower()
    if not section_heading or "summary" not in section_heading:
        return 0.0

    summary_terms = {"count", "counts", "column", "columns", "schema", "sheet", "sheets", "table", "tables", "combien"}
    return 0.14 if query_terms & summary_terms else 0.0


def _markdown_content_boost(meta: dict[str, Any], query_terms: set[str]) -> float:
    source_kind = str(meta.get("source_kind", "")).lower()
    if source_kind != "markdown":
        return 0.0

    boost = 0.0
    code_terms = {
        "code",
        "example",
        "examples",
        "snippet",
        "implementation",
        "function",
        "class",
        "api",
        "endpoint",
        "request",
        "response",
        "curl",
        "python",
        "javascript",
        "bash",
        "cli",
        "command",
        "error",
        "exception",
        "trace",
    }
    overview_terms = {
        "overview",
        "introduction",
        "intro",
        "getting",
        "started",
        "quickstart",
        "installation",
        "install",
        "setup",
        "guide",
    }
    reference_terms = {"reference", "link", "links", "url", "urls", "documentation", "docs"}

    has_code = bool(meta.get("has_code_block", False))
    has_link = bool(meta.get("has_link_target", False))

    try:
        section_level = int(meta.get("section_level", 1))
    except (TypeError, ValueError):
        section_level = 1

    if has_code and query_terms & code_terms:
        boost += 0.14

    if section_level <= 2 and query_terms & overview_terms:
        boost += 0.08

    if has_link and query_terms & reference_terms:
        boost += 0.06

    return boost


def _section_position_boost(meta: dict[str, Any]) -> float:
    try:
        section_index = int(meta.get("section_index", 0))
        section_count = int(meta.get("section_count", 0))
    except (TypeError, ValueError):
        return 0.0

    if section_count <= 1:
        return 0.0

    return 0.08 * max(0.0, 1.0 - (section_index / max(1, section_count - 1)))


def rank_search_results(
    query: str,
    docs: list[str],
    metas: list[dict[str, Any]],
    distances: list[float],
    *,
    normalize_topic: Callable[[str], str],
) -> list[RankedSearchResult]:
    query_terms = _query_terms(query, normalize_topic)
    ranked: list[RankedSearchResult] = []

    for doc, meta, distance in zip(docs, metas, distances):
        title = str(meta.get("title", "")) if isinstance(meta, dict) else ""
        section_heading = str(meta.get("section_heading", "")) if isinstance(meta, dict) else ""
        base_score = 1.0 / (1.0 + float(distance))
        heading_boost = 0.35 * _term_overlap_score(section_heading, query_terms, normalize_topic)
        title_boost = 0.2 * _term_overlap_score(title, query_terms, normalize_topic)
        source_kind = str(meta.get("source_kind", "")) if isinstance(meta, dict) else ""
        strategy = _resolve_rerank_strategy(source_kind)
        strategy_boost = strategy.additional_boost(meta, query_terms) if isinstance(meta, dict) else 0.0
        position_boost = _section_position_boost(meta) if isinstance(meta, dict) else 0.0
        site_name = str(meta.get("site_name", "")) if isinstance(meta, dict) else ""
        site_id = str(meta.get("site_id", "")) if isinstance(meta, dict) else ""
        site_boost = 0.15 * max(
            _term_overlap_score(site_name, query_terms, normalize_topic),
            _term_overlap_score(site_id, query_terms, normalize_topic),
        )
        combined_score = base_score + heading_boost + title_boost + strategy_boost + position_boost + site_boost
        ranked.append(
            RankedSearchResult(
                document=doc,
                metadata=meta,
                distance=float(distance),
                semantic_score=base_score,
                rank_score=combined_score,
            )
        )

    ranked.sort(key=lambda item: item.rank_score, reverse=True)
    return ranked


def rerank_search_results(
    query: str,
    docs: list[str],
    metas: list[dict[str, Any]],
    distances: list[float],
    *,
    normalize_topic: Callable[[str], str],
) -> tuple[list[str], list[dict[str, Any]], list[float]]:
    ranked = rank_search_results(
        query,
        docs,
        metas,
        distances,
        normalize_topic=normalize_topic,
    )
    return (
        [item.document for item in ranked],
        [item.metadata for item in ranked],
        [item.distance for item in ranked],
    )


__all__ = [
    "RankedSearchResult",
    "_markdown_content_boost",
    "_query_terms",
    "_resolve_rerank_strategy",
    "_section_position_boost",
    "_summary_section_boost",
    "_term_overlap_score",
    "format_ranked_search_results",
    "format_search_results",
    "rank_search_results",
    "rerank_search_results",
]
