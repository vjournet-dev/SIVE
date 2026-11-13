from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from ...config import CHROMA_DIR, DEFAULT_COLLECTION_NAME, site_index_state_path, site_raw_docs_path
from ...domain.core.sites import SiteDefinition
from ...domain.index.indexing import index_chunks, index_pages_incrementally, make_chunks
from ...domain.parse.loader import load_local_pages, load_remote_pages
from ...infra.web.scraper import AuthSession, CrawlProgress, DocPage, crawl_docs
from ..runtime_state.progress import format_progress_bar
from .contracts import IngestRequest
from .orchestrator import build_default_ingest_orchestrator
from .pipeline import build_default_ingest_pipeline_orchestrator


@dataclass
class IngestRunResult:
    site_id: str
    site_name: str
    pages_scraped: int
    indexed_chunks: int
    changed_pages: int
    removed_pages: int
    skipped_pages: int
    duration_seconds: float
    incremental: bool


def _default_ingest_orchestrator():
    # Build from module symbols to preserve monkeypatch-based compatibility tests.
    return build_default_ingest_orchestrator(
        load_local_pages_func=load_local_pages,
        load_remote_pages_func=load_remote_pages,
        crawl_docs_func=crawl_docs,
    )


def _default_ingest_pipeline_orchestrator():
    # Build from module symbols to preserve monkeypatch-based compatibility tests.
    return build_default_ingest_pipeline_orchestrator(
        load_pages=_default_ingest_orchestrator().load_pages,
        index_pages_incrementally_func=index_pages_incrementally,
        make_chunks_func=make_chunks,
        index_chunks_func=index_chunks,
        site_raw_docs_path_func=site_raw_docs_path,
        site_index_state_path_func=site_index_state_path,
        chroma_dir=str(CHROMA_DIR),
    )


def load_pages_for_site(
    site: SiteDefinition,
    *,
    max_pages: int,
    delay: float,
    crawl_progress_every: int,
    progress_callback: Callable[[CrawlProgress], None] | None,
    auth_session: AuthSession | None = None,
) -> list[DocPage]:
    request = IngestRequest(
        site=site,
        max_pages=max_pages,
        delay=delay,
        crawl_progress_every=crawl_progress_every,
        progress_callback=progress_callback,
        auth_session=auth_session,
    )
    return _default_ingest_orchestrator().load_pages(request)


def run_ingest_for_site(
    site: SiteDefinition,
    *,
    incremental: bool = True,
    max_pages: int = 1200,
    delay: float = 0.2,
    crawl_progress_every: int = 25,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    reset_collection: bool = False,
    chunk_size: int = 1200,
    overlap: int = 200,
    progress_callback: Callable[[CrawlProgress], None] | None = None,
    auth_session: AuthSession | None = None,
) -> IngestRunResult:
    pipeline_result = _default_ingest_pipeline_orchestrator().run(
        site,
        incremental=incremental,
        max_pages=max_pages,
        delay=delay,
        crawl_progress_every=crawl_progress_every,
        collection_name=collection_name,
        embedding_model_name=embedding_model_name,
        reset_collection=reset_collection,
        chunk_size=chunk_size,
        overlap=overlap,
        progress_callback=progress_callback,
        auth_session=auth_session,
    )

    return IngestRunResult(
        site_id=site.site_id,
        site_name=site.site_name,
        pages_scraped=pipeline_result.pages_scraped,
        indexed_chunks=pipeline_result.indexed_chunks,
        changed_pages=pipeline_result.changed_pages,
        removed_pages=pipeline_result.removed_pages,
        skipped_pages=pipeline_result.skipped_pages,
        duration_seconds=pipeline_result.duration_seconds,
        incremental=pipeline_result.incremental,
    )


# Local selective update for existing indexed local documentation
# Reuses load_local_pages from parse layer, make_chunks from index layer


def _normalize_path_parts(path: Path) -> tuple[str, ...]:
    return tuple(part.strip().lower() for part in path.parts if part and part not in {"/", "\\"})


def _extract_path_parts_from_file_url(source_url: str) -> tuple[str, ...] | None:
    parsed = urlparse(source_url)
    if parsed.scheme != "file":
        return None
    local_path = Path(url2pathname(unquote(parsed.path)))
    parts = _normalize_path_parts(local_path)
    return parts or None


def _candidate_key_parts(candidate_path: Path, base_path: Path, is_dir_mode: bool) -> tuple[str, ...]:
    if is_dir_mode:
        relative = candidate_path.resolve().relative_to(base_path.resolve())
        return _normalize_path_parts(relative)
    parent_name = candidate_path.parent.name.strip().lower()
    filename = candidate_path.name.strip().lower()
    return (parent_name, filename) if parent_name else (filename,)


def update_existing_local_site(
    target_path: str,
    *,
    collection: Any,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    chunk_size: int = 1200,
    overlap: int = 200,
    load_local_pages_func: Callable[..., list[DocPage]] = load_local_pages,
    site_index_state_path_func: Callable[[str], Path] = site_index_state_path,
) -> dict[str, Any]:
    """Update indexed local documents at target_path incrementally.

    Matches local files against indexed file:// URLs by path parts,
    compares content hashes, and re-indexes only changed documents.
    Uses existing load_local_pages and make_chunks to maintain architecture coherence.
    """
    resolved_target = Path(target_path).expanduser().resolve()

    if not resolved_target.exists():
        return {
            "status": "no_match",
            "mode": "local_selective_update",
            "target_path": str(resolved_target),
            "checked": 0,
            "matched": 0,
            "updated": 0,
            "skipped": 0,
            "collision_count": 0,
            "changed_pages": 0,
            "unchanged_pages": 0,
            "progress_percent": 100,
            "progress_bar": format_progress_bar(100),
            "message": "Local path does not exist. Nothing was updated.",
        }

    is_dir_mode = resolved_target.is_dir()
    try:
        loaded_pages = load_local_pages_func(
            str(resolved_target),
            site_id="local-update-candidate",
            site_name=resolved_target.name,
        )
    except (ValueError, FileNotFoundError):
        loaded_pages = []

    if not loaded_pages:
        return {
            "status": "no_match",
            "mode": "local_selective_update",
            "target_path": str(resolved_target),
            "checked": 0,
            "matched": 0,
            "updated": 0,
            "skipped": 0,
            "collision_count": 0,
            "changed_pages": 0,
            "unchanged_pages": 0,
            "progress_percent": 100,
            "progress_bar": format_progress_bar(100),
            "message": "No supported local files found to evaluate.",
        }

    # Fetch all indexed metadata with file:// URLs
    indexed_result = collection.get(include=["metadatas"])
    raw_metas = indexed_result.get("metadatas", []) if isinstance(indexed_result, dict) else []
    metas = [m for m in raw_metas if isinstance(m, dict)] if isinstance(raw_metas, list) else []

    indexed_by_url: dict[str, dict[str, Any]] = {}
    for meta in metas:
        source_url = str(meta.get("source_url", "")).strip()
        site_id = str(meta.get("site_id", "")).strip()
        if not source_url or not site_id or urlparse(source_url).scheme != "file":
            continue
        site_name = str(meta.get("site_name", site_id)).strip() or site_id
        indexed_by_url[source_url] = {
            "source_url": source_url,
            "site_id": site_id,
            "site_name": site_name,
            "content_hash": str(meta.get("content_hash", "")).strip(),
            "parts": _extract_path_parts_from_file_url(source_url),
        }

    # Build candidates with normalized key parts for matching
    candidates = []
    for page in loaded_pages:
        candidate_parts = _extract_path_parts_from_file_url(page.url)
        if candidate_parts is None:
            continue
        candidate_path = Path(url2pathname(unquote(urlparse(page.url).path)))
        key_parts = _candidate_key_parts(candidate_path, resolved_target, is_dir_mode)
        if key_parts:
            candidates.append((page, key_parts))

    checked = len(candidates)
    if checked == 0:
        return {
            "status": "no_match",
            "mode": "local_selective_update",
            "target_path": str(resolved_target),
            "checked": 0,
            "matched": 0,
            "updated": 0,
            "skipped": 0,
            "collision_count": 0,
            "changed_pages": 0,
            "unchanged_pages": 0,
            "progress_percent": 100,
            "progress_bar": format_progress_bar(100),
            "message": "No valid local file candidates found after parsing.",
        }

    # Match candidates against indexed URLs by path parts
    matched_pages_by_url: dict[str, DocPage] = {}
    matched_existing_hashes: dict[str, str] = {}
    matched_candidates = 0
    collision_count = 0

    for page, key_parts in candidates:
        key_len = len(key_parts)
        matching_entries = [
            entry
            for entry in indexed_by_url.values()
            if isinstance(entry.get("parts"), tuple)
            and len(entry["parts"]) >= key_len
            and tuple(entry["parts"][-key_len:]) == key_parts
        ]
        if not matching_entries:
            continue
        matched_candidates += 1
        if len(matching_entries) > 1:
            collision_count += len(matching_entries) - 1
        for entry in matching_entries:
            source_url = str(entry["source_url"])
            matched_existing_hashes[source_url] = str(entry.get("content_hash", "")).strip()
            matched_pages_by_url[source_url] = DocPage(
                site_id=str(entry["site_id"]),
                site_name=str(entry["site_name"]),
                url=source_url,
                title=page.title,
                content=page.content,
                content_hash=page.content_hash,
                sections=page.sections,
            )

    if not matched_pages_by_url:
        return {
            "status": "no_match",
            "mode": "local_selective_update",
            "target_path": str(resolved_target),
            "checked": checked,
            "matched": 0,
            "updated": 0,
            "skipped": checked,
            "collision_count": 0,
            "changed_pages": 0,
            "unchanged_pages": 0,
            "progress_percent": 100,
            "progress_bar": format_progress_bar(100),
            "message": "No indexed local documents matched this path. Nothing was updated.",
        }

    # Detect changed vs unchanged by content hash
    changed_pages: list[DocPage] = []
    unchanged_pages = 0
    for source_url, page in matched_pages_by_url.items():
        existing_hash = matched_existing_hashes.get(source_url, "")
        if existing_hash and existing_hash == page.content_hash:
            unchanged_pages += 1
            continue
        changed_pages.append(page)

    # Delete old chunks for changed pages, re-index with make_chunks
    for page in changed_pages:
        collection.delete(where={"source_url": page.url})

    changed_chunks = make_chunks(changed_pages, chunk_size=chunk_size, overlap=overlap)
    indexed_chunks = 0
    if changed_chunks:
        collection.upsert(
            ids=[chunk.chunk_id for chunk in changed_chunks],
            documents=[chunk.text for chunk in changed_chunks],
            metadatas=[
                {
                    "source_url": chunk.source_url,
                    "title": chunk.title,
                    "chunk_index": chunk.chunk_index,
                    "section_heading": chunk.section_heading,
                    "content_hash": chunk.content_hash,
                    "site_id": chunk.site_id,
                    "site_name": chunk.site_name,
                    "page_number": chunk.page_number,
                    "source_kind": chunk.source_kind,
                    "section_index": chunk.section_index,
                    "section_count": chunk.section_count,
                    "section_level": chunk.section_level,
                    "has_code_block": chunk.has_code_block,
                    "has_link_target": chunk.has_link_target,
                }
                for chunk in changed_chunks
            ],
        )
        indexed_chunks = len(changed_chunks)

    # Update state files for all affected sites
    pages_by_site: dict[str, list[DocPage]] = {}
    for page in matched_pages_by_url.values():
        pages_by_site.setdefault(page.site_id, []).append(page)
    for site_id, site_pages in pages_by_site.items():
        state_path = site_index_state_path_func(site_id)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state: dict[str, dict[str, str]] = {}
        if state_path.exists():
            try:
                raw = json.loads(state_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    state = {str(url): value for url, value in raw.items() if isinstance(url, str) and isinstance(value, dict)}
            except (OSError, json.JSONDecodeError):
                state = {}
        for page in site_pages:
            state[page.url] = {
                "title": page.title,
                "content_hash": page.content_hash,
                "site_id": page.site_id,
                "site_name": page.site_name,
            }
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    updated_site_ids = sorted({page.site_id for page in changed_pages})
    updated_count = len(changed_pages)
    matched_count = len(matched_pages_by_url)
    skipped_count = max(0, checked - matched_candidates) + unchanged_pages

    return {
        "status": "ok" if updated_count > 0 else "no_change",
        "mode": "local_selective_update",
        "target_path": str(resolved_target),
        "checked": checked,
        "matched": matched_count,
        "updated": updated_count,
        "skipped": skipped_count,
        "collision_count": collision_count,
        "changed_pages": updated_count,
        "unchanged_pages": unchanged_pages,
        "indexed_chunks": indexed_chunks,
        "updated_site_ids": updated_site_ids,
        "progress_percent": 100,
        "progress_bar": format_progress_bar(100),
        "message": (
            "Existing local documentation entries were updated incrementally."
            if updated_count > 0
            else "All matched local documentation entries are already up to date."
        ),
    }
