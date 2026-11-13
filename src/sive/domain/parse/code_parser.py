"""Code section extraction utilities for parsed documents."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CodeSection:
    """Represents a code symbol extracted from a source file."""

    name: str
    start_line: int
    signature: str


def extract_code_sections(content: str, language: str | None = None) -> list[CodeSection]:
    """Extract code sections (functions/classes) from source content.

    Current implementation is intentionally conservative and returns no symbols.
    The typed return keeps downstream parser code safe for static analysis.
    """
    _ = (content, language)
    return []
