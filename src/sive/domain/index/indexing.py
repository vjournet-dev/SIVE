from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import chromadb
from chromadb import Collection

from ...infra.vector_store.chroma import get_collection
from ...infra.vector_store.embedding_loader import get_sentence_transformer_embedding_function
from ...infra.web.scraper import DocPage, DocSection


@dataclass
class DocChunk:
    chunk_id: str
    text: str
    source_url: str
    title: str
    chunk_index: int
    section_heading: str
    content_hash: str
    site_id: str
    site_name: str
    page_number: int | None
    source_kind: str
    section_index: int
    section_count: int
    section_level: int
    has_code_block: bool
    has_link_target: bool


@dataclass
class IncrementalIndexResult:
    indexed_chunks: int
    changed_pages: int
    removed_pages: int
    skipped_pages: int


class _ChunkStrategy(Protocol):
    @property
    def name(self) -> str:
        ...

    def chunk(self, text: str, *, chunk_size: int, overlap: int) -> list[str]:
        ...


IndexProgressCallback = Callable[[int, int], None] | None


@dataclass(frozen=True)
class _GenericChunkStrategy:
    name: str = "generic"

    def chunk(self, text: str, *, chunk_size: int, overlap: int) -> list[str]:
        return chunk_text(text, chunk_size=chunk_size, overlap=overlap)


@dataclass(frozen=True)
class _TableChunkStrategy:
    name: str = "table"

    def chunk(self, text: str, *, chunk_size: int, overlap: int) -> list[str]:
        # Tabular rows are easier to consume without overlap duplicates.
        return chunk_text(text, chunk_size=chunk_size, overlap=0)


@dataclass(frozen=True)
class _PdfChunkStrategy:
    name: str = "pdf"

    def chunk(self, text: str, *, chunk_size: int, overlap: int) -> list[str]:
        capped_overlap = min(overlap, max(0, chunk_size // 6))
        return chunk_text(text, chunk_size=chunk_size, overlap=capped_overlap)


@dataclass(frozen=True)
class _MarkdownChunkStrategy:
    name: str = "markdown"

    def chunk(self, text: str, *, chunk_size: int, overlap: int) -> list[str]:
        return chunk_text(text, chunk_size=chunk_size, overlap=overlap)


@dataclass(frozen=True)
class _WordChunkStrategy:
    name: str = "word"

    def chunk(self, text: str, *, chunk_size: int, overlap: int) -> list[str]:
        return chunk_text(text, chunk_size=chunk_size, overlap=overlap)


_DEFAULT_CHUNK_STRATEGY: _ChunkStrategy = _GenericChunkStrategy()
_CHUNK_STRATEGIES_BY_SOURCE_KIND: dict[str, _ChunkStrategy] = {
    "markdown": _MarkdownChunkStrategy(),
    "csv": _TableChunkStrategy(),
    "xlsx": _TableChunkStrategy(),
    "pdf": _PdfChunkStrategy(),
    "docx": _WordChunkStrategy(),
}


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")

    chunks: list[str] = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunks.append(text[start:end])
        if end == text_len:
            break
        start = end - overlap
    return chunks


def _stable_page_prefix(page: DocPage) -> str:
    return hashlib.sha1(f"{page.site_id}:{page.url}".encode()).hexdigest()[:16]


def _extract_page_number(section: DocSection) -> int | None:
    heading = (section.heading or "").strip()
    if not heading.lower().startswith("page "):
        return None
    suffix = heading[5:].strip()
    return int(suffix) if suffix.isdigit() else None


def _build_section_text(title: str, section: DocSection) -> str:
    if section.heading:
        return f"{title}\n{section.heading}\n\n{section.content}".strip()
    return f"{title}\n\n{section.content}".strip()


def _contains_link_target(text: str) -> bool:
    return bool(re.search(r"(?:https?|mailto):\S+", text, flags=re.IGNORECASE))


def _page_to_sections(page: DocPage) -> list[DocSection]:
    if page.sections:
        return page.sections
    return [DocSection(heading=page.title or "Introduction", level=1, content=page.content)]


def _infer_source_kind(page: DocPage) -> str:
    parsed = urlparse(page.url)
    suffix = Path(parsed.path).suffix.lower()

    if suffix == ".csv":
        return "csv"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".docx":
        return "docx"
    if suffix == ".json":
        return "json"
    if suffix == ".xlsx":
        return "xlsx"
    if suffix in {".html", ".htm"}:
        return "html"
    if parsed.scheme == "file":
        return "local"
    return "html"


def _resolve_chunk_strategy(source_kind: str) -> _ChunkStrategy:
    return _CHUNK_STRATEGIES_BY_SOURCE_KIND.get(source_kind.lower(), _DEFAULT_CHUNK_STRATEGY)


def make_chunks(pages: list[DocPage], chunk_size: int = 1200, overlap: int = 200) -> list[DocChunk]:
    out: list[DocChunk] = []
    for page in pages:
        page_prefix = _stable_page_prefix(page)
        chunk_counter = 0
        sections = _page_to_sections(page)
        source_kind = _infer_source_kind(page)
        strategy = _resolve_chunk_strategy(source_kind)
        for section_index, section in enumerate(sections):
            page_number = _extract_page_number(section)
            section_level = max(1, int(section.level)) if isinstance(section.level, int) else 1
            parts = strategy.chunk(_build_section_text(page.title, section), chunk_size=chunk_size, overlap=overlap)
            for part in parts:
                has_code_block = "[code" in part.lower() or "[/code]" in part.lower()
                has_link_target = _contains_link_target(part)
                out.append(
                    DocChunk(
                        chunk_id=f"doc-{page_prefix}-chunk-{chunk_counter}",
                        text=part,
                        source_url=page.url,
                        title=page.title,
                        chunk_index=chunk_counter,
                        section_heading=section.heading,
                        content_hash=page.content_hash,
                        site_id=page.site_id,
                        site_name=page.site_name,
                        page_number=page_number,
                        source_kind=source_kind,
                        section_index=section_index,
                        section_count=len(sections),
                        section_level=section_level,
                        has_code_block=has_code_block,
                        has_link_target=has_link_target,
                    )
                )
                chunk_counter += 1
    return out


def load_index_state(state_path: Path) -> dict[str, dict[str, str]]:
    if not state_path.exists():
        return {}
    with state_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_index_state(state_path: Path, pages: list[DocPage]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        page.url: {
            "title": page.title,
            "content_hash": page.content_hash,
            "site_id": page.site_id,
            "site_name": page.site_name,
        }
        for page in pages
    }
    with state_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False)


def select_incremental_pages(
    pages: list[DocPage],
    previous_state: dict[str, dict[str, str]],
) -> tuple[list[DocPage], list[str], int]:
    changed_pages: list[DocPage] = []
    skipped_pages = 0
    current_urls = {page.url for page in pages}

    for page in pages:
        previous = previous_state.get(page.url)
        if not previous or previous.get("content_hash") != page.content_hash:
            changed_pages.append(page)
        else:
            skipped_pages += 1

    removed_urls = sorted(set(previous_state) - current_urls)
    return changed_pages, removed_urls, skipped_pages


def _dedupe_pages_by_url(pages: list[DocPage]) -> list[DocPage]:
    seen: set[str] = set()
    unique: list[DocPage] = []
    for page in pages:
        if page.url in seen:
            continue
        seen.add(page.url)
        unique.append(page)
    return unique


def _dedupe_chunks_by_id(chunks: list[DocChunk]) -> list[DocChunk]:
    seen: set[str] = set()
    unique: list[DocChunk] = []
    for chunk in chunks:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        unique.append(chunk)
    return unique


def _get_collection(
    chroma_dir: Path,
    collection_name: str,
    embedding_model_name: str,
    reset_collection: bool,
) -> Collection:
    return get_collection(
        chroma_dir,
        collection_name,
        embedding_model_name,
        chromadb_module=chromadb,
        get_collection_from_client_func=_get_collection_from_client,
        reset_collection=reset_collection,
    )


def _get_collection_from_client(client: object, collection_name: str, embedding_model_name: str, *, reset_collection: bool = False) -> Collection:
    from ...infra.vector_store.chroma import get_collection_from_client

    return get_collection_from_client(
        client,
        collection_name,
        embedding_model_name,
        get_sentence_transformer_embedding_function_func=get_sentence_transformer_embedding_function,
        reset_collection=reset_collection,
    )


def _upsert_chunks(
    collection: Collection,
    chunks: list[DocChunk],
    batch_size: int,
    progress_callback: IndexProgressCallback = None,
) -> int:
    deduped_chunks = _dedupe_chunks_by_id(chunks)
    total_chunks = len(deduped_chunks)

    if progress_callback is not None:
        progress_callback(0, total_chunks)

    indexed_so_far = 0

    for i in range(0, len(deduped_chunks), batch_size):
        batch = deduped_chunks[i : i + batch_size]
        collection.upsert(
            ids=[chunk.chunk_id for chunk in batch],
            documents=[chunk.text for chunk in batch],
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
                for chunk in batch
            ],
        )
        indexed_so_far += len(batch)
        if progress_callback is not None:
            progress_callback(indexed_so_far, total_chunks)

    return total_chunks


def index_chunks(
    chunks: list[DocChunk],
    chroma_dir: Path,
    collection_name: str,
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    reset_collection: bool = False,
    batch_size: int = 128,
    progress_callback: IndexProgressCallback = None,
) -> int:
    collection = _get_collection(chroma_dir, collection_name, embedding_model_name, reset_collection)
    return _upsert_chunks(collection, chunks, batch_size, progress_callback)


def index_pages_incrementally(
    pages: list[DocPage],
    chroma_dir: Path,
    collection_name: str,
    state_path: Path,
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    reset_collection: bool = False,
    batch_size: int = 128,
    chunk_size: int = 1200,
    overlap: int = 200,
    progress_callback: IndexProgressCallback = None,
) -> IncrementalIndexResult:
    unique_pages = _dedupe_pages_by_url(pages)
    previous_state = {} if reset_collection else load_index_state(state_path)
    changed_pages, removed_urls, skipped_pages = select_incremental_pages(unique_pages, previous_state)
    collection = _get_collection(chroma_dir, collection_name, embedding_model_name, reset_collection)

    if removed_urls:
        for url in removed_urls:
            collection.delete(where={"source_url": url})

    if changed_pages:
        for page in changed_pages:
            collection.delete(where={"source_url": page.url})
        changed_chunks = make_chunks(changed_pages, chunk_size=chunk_size, overlap=overlap)
        indexed_count = _upsert_chunks(collection, changed_chunks, batch_size, progress_callback)
    else:
        indexed_count = 0
        if progress_callback is not None:
            progress_callback(0, 0)

    save_index_state(state_path, unique_pages)
    return IncrementalIndexResult(
        indexed_chunks=indexed_count,
        changed_pages=len(changed_pages),
        removed_pages=len(removed_urls),
        skipped_pages=skipped_pages,
    )
