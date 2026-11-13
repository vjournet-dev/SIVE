from __future__ import annotations

import pytest

from sive.domain.chunk.registry import ChunkStrategyRegistry
from sive.domain.parse.contracts import ParsedDocument
from sive.domain.parse.format_registry import FormatParserRegistry
from sive.domain.rerank.registry import RerankStrategyRegistry


class _MarkdownParser:
    name = "markdown-parser"

    def can_handle(self, source: str, metadata: dict[str, object] | None = None) -> bool:
        return source.lower().endswith(".md")

    def parse(self, source: str, payload: bytes, metadata: dict[str, object] | None = None) -> ParsedDocument:
        return ParsedDocument(
            source=source,
            format_name="markdown",
            title="doc",
            content=payload.decode("utf-8", errors="ignore"),
            metadata=dict(metadata or {}),
        )


class _DefaultParser:
    name = "default-parser"

    def can_handle(self, source: str, metadata: dict[str, object] | None = None) -> bool:
        return True

    def parse(self, source: str, payload: bytes, metadata: dict[str, object] | None = None) -> ParsedDocument:
        return ParsedDocument(source=source, format_name="generic", title="doc", content="", metadata={})


class _Chunker:
    def __init__(self, name: str):
        self.name = name

    def chunk(self, document: ParsedDocument, *, chunk_size: int, overlap: int) -> list[str]:
        return [document.content[:chunk_size]]


class _Reranker:
    def __init__(self, name: str):
        self.name = name

    def rerank(self, query: str, docs: list[str], metas: list[dict[str, object]], distances: list[float]):
        return docs, metas, distances


def test_format_parser_registry_resolves_first_matching_plugin():
    registry = FormatParserRegistry()
    default = _DefaultParser()
    markdown = _MarkdownParser()
    registry.register(markdown)
    registry.register(default)

    resolved = registry.resolve("readme.md")

    assert resolved.name == "markdown-parser"


def test_format_parser_registry_raises_when_no_parser_matches():
    class _NeverParser:
        name = "never"

        def can_handle(self, source: str, metadata: dict[str, object] | None = None) -> bool:
            return False

        def parse(self, source: str, payload: bytes, metadata: dict[str, object] | None = None) -> ParsedDocument:
            return ParsedDocument(source=source, format_name="none", title="", content="", metadata={})

    registry = FormatParserRegistry()
    registry.register(_NeverParser())

    with pytest.raises(ValueError, match="No format parser plugin"):
        registry.resolve("unknown.bin")


def test_chunk_registry_resolves_by_format_and_falls_back_to_default():
    registry = ChunkStrategyRegistry()
    markdown = _Chunker("markdown-chunker")
    fallback = _Chunker("fallback-chunker")
    registry.register("markdown", markdown)
    registry.set_default(fallback)

    assert registry.resolve("markdown").name == "markdown-chunker"
    assert registry.resolve("unknown-format").name == "fallback-chunker"


def test_chunk_registry_raises_without_matching_or_default():
    registry = ChunkStrategyRegistry()
    with pytest.raises(ValueError, match="No chunk strategy registered"):
        registry.resolve("markdown")


def test_rerank_registry_resolves_by_format_and_falls_back_to_default():
    registry = RerankStrategyRegistry()
    markdown = _Reranker("markdown-reranker")
    fallback = _Reranker("fallback-reranker")
    registry.register("markdown", markdown)
    registry.set_default(fallback)

    assert registry.resolve("markdown").name == "markdown-reranker"
    assert registry.resolve("json").name == "fallback-reranker"


def test_rerank_registry_raises_without_matching_or_default():
    registry = RerankStrategyRegistry()
    with pytest.raises(ValueError, match="No rerank strategy registered"):
        registry.resolve("markdown")
