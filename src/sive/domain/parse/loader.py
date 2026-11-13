from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from ...domain.auth.session import AuthenticationRequiredError, AuthSession
from ...domain.parse.code_parser import extract_code_sections
from ...infra.web.scraper import DocPage, DocSection, extract_page_content, hash_content

SUPPORTED_LOCAL_FILE_EXTENSIONS = {
    ".csv",
    ".htm",
    ".html",
    ".json",
    ".md",
    ".markdown",
    ".pdf",
    ".docx",
    ".xlsx",
    # Code files
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".sql",
    ".sh",
    ".bash",
    ".rb",
    ".php",
    ".cpp",
    ".c",
    ".cs",
    ".kt",
}
SUPPORTED_REMOTE_FILE_EXTENSIONS = {".csv", ".json", ".md", ".markdown", ".pdf", ".docx", ".xlsx"}
DEFAULT_MAX_REMOTE_BYTES = 25 * 1024 * 1024  # 25 MiB hard ceiling per remote document.

_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_MARKDOWN_CODE_FENCE_RE = re.compile(r"^(```+|~~~+)")
_MARKDOWN_SETEXT_H1_RE = re.compile(r"^\s*=+\s*$")
_MARKDOWN_SETEXT_H2_RE = re.compile(r"^\s*-+\s*$")


LocalParserLoader = Callable[..., DocPage | None]
RemoteParserLoader = Callable[..., DocPage | None]


@dataclass(frozen=True)
class LocalFormatParserPlugin:
    name: str
    suffixes: tuple[str, ...]
    loader_name: str

    def can_handle(self, suffix: str) -> bool:
        return suffix in self.suffixes

    def parse(self, file_path: Path, *, site_id: str, site_name: str) -> DocPage | None:
        loader = cast(LocalParserLoader, globals()[self.loader_name])
        return loader(file_path, site_id=site_id, site_name=site_name)


@dataclass(frozen=True)
class RemoteFormatParserPlugin:
    name: str
    suffixes: tuple[str, ...]
    loader_name: str

    def can_handle(self, suffix: str) -> bool:
        return suffix in self.suffixes

    def parse(self, response: httpx.Response, *, site_id: str, site_name: str) -> DocPage | None:
        loader = cast(RemoteParserLoader, globals()[self.loader_name])
        return loader(response, site_id=site_id, site_name=site_name)


def is_supported_local_source(path: Path) -> bool:
    if path.is_dir():
        return True
    return path.suffix.lower() in SUPPORTED_LOCAL_FILE_EXTENSIONS


def _supported_remote_suffix_from_url(source_url: str) -> str | None:
    parsed = urlparse(source_url.strip())
    suffix = Path(parsed.path).suffix.lower()
    if suffix in SUPPORTED_REMOTE_FILE_EXTENSIONS:
        return suffix

    query = parse_qs(parsed.query)
    for key in ("id", "file", "SourceUrl", "sourceurl"):
        for raw_value in query.get(key, []):
            candidate = unquote(str(raw_value or "")).strip()
            if not candidate:
                continue
            candidate_path = urlparse(candidate).path or candidate
            candidate_suffix = Path(candidate_path).suffix.lower()
            if candidate_suffix in SUPPORTED_REMOTE_FILE_EXTENSIONS:
                return candidate_suffix

    return None


def _iter_supported_files(source_path: Path) -> list[Path]:
    if source_path.is_file():
        if not is_supported_local_source(source_path):
            raise ValueError(
                "Unsupported local file type. Supported formats: .csv, .html, .htm, .json, .md, .markdown, .pdf, .docx, .xlsx"
            )
        return [source_path]

    if source_path.is_dir():
        files = sorted(
            path
            for path in source_path.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_LOCAL_FILE_EXTENSIONS
        )
        if not files:
            raise ValueError("No supported local files found in directory.")
        return files

    raise FileNotFoundError(f"Local source not found: {source_path}")


def _build_file_page(file_path: Path, *, site_id: str, site_name: str, text: str, title: str) -> DocPage | None:
    cleaned_text = text.strip()
    if not cleaned_text:
        return None

    return DocPage(
        site_id=site_id,
        site_name=site_name,
        url=file_path.resolve().as_uri(),
        title=title,
        content=cleaned_text,
        content_hash=hash_content(cleaned_text),
        sections=[DocSection(heading=title, level=1, content=cleaned_text)],
    )


def _build_file_page_with_sections(
    file_path: Path,
    *,
    site_id: str,
    site_name: str,
    title: str,
    sections: list[DocSection],
) -> DocPage | None:
    filtered_sections = [section for section in sections if section.content.strip()]
    if not filtered_sections:
        return None

    full_text = "\n\n".join(
        f"{section.heading}\n{section.content}".strip() if section.heading else section.content.strip()
        for section in filtered_sections
    ).strip()
    if not full_text:
        return None

    return DocPage(
        site_id=site_id,
        site_name=site_name,
        url=file_path.resolve().as_uri(),
        title=title,
        content=full_text,
        content_hash=hash_content(full_text),
        sections=filtered_sections,
    )


def _build_remote_page(source_url: str, *, site_id: str, site_name: str, text: str, title: str) -> DocPage | None:
    cleaned_text = text.strip()
    if not cleaned_text:
        return None

    return DocPage(
        site_id=site_id,
        site_name=site_name,
        url=source_url,
        title=title,
        content=cleaned_text,
        content_hash=hash_content(cleaned_text),
        sections=[DocSection(heading=title, level=1, content=cleaned_text)],
    )


def _build_remote_page_with_sections(
    source_url: str,
    *,
    site_id: str,
    site_name: str,
    title: str,
    sections: list[DocSection],
) -> DocPage | None:
    filtered_sections = [section for section in sections if section.content.strip()]
    if not filtered_sections:
        return None

    full_text = "\n\n".join(
        f"{section.heading}\n{section.content}".strip() if section.heading else section.content.strip()
        for section in filtered_sections
    ).strip()
    if not full_text:
        return None

    return DocPage(
        site_id=site_id,
        site_name=site_name,
        url=source_url,
        title=title,
        content=full_text,
        content_hash=hash_content(full_text),
        sections=filtered_sections,
    )


def _json_to_text(value: Any, *, source_name: str) -> str:
    try:
        pretty = json.dumps(value, ensure_ascii=False, indent=2)
    except TypeError:
        pretty = str(value)
    return f"{source_name}\n\n{pretty}".strip()


def _json_scalar_to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def _flatten_json_lines(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        if not value:
            return [f"{prefix}: {{}}"] if prefix else ["{}"]
        lines: list[str] = []
        for key, nested in value.items():
            nested_prefix = f"{prefix}.{key}" if prefix else str(key)
            lines.extend(_flatten_json_lines(nested, nested_prefix))
        return lines

    if isinstance(value, list):
        if not value:
            return [f"{prefix}: []"] if prefix else ["[]"]
        list_lines: list[str] = []
        for index, nested in enumerate(value):
            nested_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            list_lines.extend(_flatten_json_lines(nested, nested_prefix))
        return list_lines

    scalar = _json_scalar_to_text(value)
    return [f"{prefix}: {scalar}" if prefix else scalar]


def _json_to_sections(value: Any, *, source_name: str) -> list[DocSection]:
    if isinstance(value, dict) and value:
        sections: list[DocSection] = []
        for key, nested in value.items():
            lines = _flatten_json_lines(nested)
            content = "\n".join(lines).strip()
            if content:
                sections.append(DocSection(heading=str(key), level=1, content=content))
        return sections

    if isinstance(value, list) and value:
        sections = []
        for index, nested in enumerate(value):
            item_lines = _flatten_json_lines(nested)
            content = "\n".join(item_lines).strip()
            if content:
                sections.append(DocSection(heading=f"Item {index + 1}", level=1, content=content))
        return sections

    return [DocSection(heading=source_name, level=1, content="\n".join(_flatten_json_lines(value)).strip())]


def _load_html_file(file_path: Path, *, site_id: str, site_name: str) -> DocPage | None:
    html = file_path.read_text(encoding="utf-8", errors="ignore")
    return extract_page_content(html, file_path.resolve().as_uri(), site_id=site_id, site_name=site_name)


def _load_json_file(file_path: Path, *, site_id: str, site_name: str) -> DocPage | None:
    data = json.loads(file_path.read_text(encoding="utf-8"))
    return _build_file_page_with_sections(
        file_path,
        site_id=site_id,
        site_name=site_name,
        title=file_path.name,
        sections=_json_to_sections(data, source_name=file_path.name),
    )


def _markdown_inline_to_text(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        return ""

    # Keep link targets because they often contain high-signal technical tokens.
    normalized = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"\1 (\2)", normalized)
    normalized = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", normalized)
    normalized = re.sub(r"<((?:https?|mailto):[^>]+)>", r"\1", normalized)
    normalized = re.sub(r"`([^`]+)`", r"\1", normalized)
    # Remove emphasis markers while preserving intraword underscores (e.g., MY_VAR).
    normalized = re.sub(r"(?<!\w)(\*\*|__)([^\n]+?)\1(?!\w)", r"\2", normalized)
    normalized = re.sub(r"(?<!\w)(\*|_)([^\n]+?)\1(?!\w)", r"\2", normalized)
    normalized = normalized.replace("~~", "")
    return normalized.strip()


def _markdown_line_to_text(line: str) -> str:
    cleaned = line.strip()
    if not cleaned:
        return ""

    cleaned = re.sub(r"^\s{0,3}>\s?", "", cleaned)
    cleaned = re.sub(r"^\s{0,3}(?:[-*+])\s+\[[ xX]\]\s+", "", cleaned)
    cleaned = re.sub(r"^\s{0,3}(?:[-*+])\s+", "", cleaned)
    cleaned = re.sub(r"^\s{0,3}\d+[.)]\s+", "", cleaned)

    if "|" in cleaned:
        maybe_table = cleaned.strip().strip("|").strip()
        if maybe_table:
            cells = [cell.strip() for cell in maybe_table.split("|")]
            if cells and all(cells):
                # Skip markdown table separator rows like | --- | :---: |
                if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                    return ""
                cleaned = " | ".join(cells)

    return _markdown_inline_to_text(cleaned)


def _strip_markdown_front_matter(content: str) -> str:
    if not content.startswith("---"):
        return content

    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return content

    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[index + 1 :]).lstrip("\n")
    return content


def _setext_heading_level(line: str) -> int | None:
    if _MARKDOWN_SETEXT_H1_RE.match(line):
        return 1
    if _MARKDOWN_SETEXT_H2_RE.match(line):
        return 2
    return None


def _markdown_to_sections(content: str, *, fallback_heading: str) -> list[DocSection]:
    content = _strip_markdown_front_matter(content)
    lines = content.splitlines()

    sections: list[DocSection] = []
    current_heading = fallback_heading
    current_level = 1
    current_lines: list[str] = []
    in_code_block = False
    code_fence = ""

    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped_line = raw_line.strip()

        fence_match = _MARKDOWN_CODE_FENCE_RE.match(stripped_line)
        if fence_match:
            marker = fence_match.group(1)
            if not in_code_block:
                in_code_block = True
                code_fence = marker
                language = stripped_line[len(marker) :].strip()
                current_lines.append(f"[code:{language}]" if language else "[code]")
            elif stripped_line.startswith(code_fence):
                in_code_block = False
                code_fence = ""
                current_lines.append("[/code]")
            index += 1
            continue

        if not in_code_block and index + 1 < len(lines):
            setext_level = _setext_heading_level(lines[index + 1].strip())
            heading_text = _markdown_inline_to_text(stripped_line)
            if setext_level is not None and heading_text:
                if current_lines:
                    section_text = "\n".join(current_lines).strip()
                    if section_text:
                        sections.append(DocSection(heading=current_heading, level=current_level, content=section_text))
                current_heading = heading_text
                current_level = setext_level
                current_lines = []
                index += 2
                continue

        if not in_code_block and re.fullmatch(r"\s*([-*_])(?:\s*\1){2,}\s*", raw_line):
            index += 1
            continue

        if not in_code_block:
            heading_match = _MARKDOWN_HEADING_RE.match(stripped_line)
            if heading_match:
                if current_lines:
                    section_text = "\n".join(current_lines).strip()
                    if section_text:
                        sections.append(DocSection(heading=current_heading, level=current_level, content=section_text))
                current_heading = _markdown_inline_to_text(heading_match.group(2)) or fallback_heading
                current_level = len(heading_match.group(1))
                current_lines = []
                index += 1
                continue

            cleaned_line = _markdown_line_to_text(raw_line)
        else:
            cleaned_line = raw_line.rstrip()

        if cleaned_line:
            current_lines.append(cleaned_line)
        elif current_lines and current_lines[-1] != "":
            current_lines.append("")

        index += 1

    if current_lines:
        section_text = "\n".join(current_lines).strip()
        if section_text:
            sections.append(DocSection(heading=current_heading, level=current_level, content=section_text))

    return sections


def _load_markdown_file(file_path: Path, *, site_id: str, site_name: str) -> DocPage | None:
    markdown = file_path.read_text(encoding="utf-8", errors="ignore")
    return _build_file_page_with_sections(
        file_path,
        site_id=site_id,
        site_name=site_name,
        title=file_path.name,
        sections=_markdown_to_sections(markdown, fallback_heading=file_path.name),
    )


def _csv_rows_to_sections(rows: list[list[str]], *, source_name: str) -> list[DocSection]:
    if not rows:
        return []

    header = rows[0]
    data_rows = rows[1:] if header else rows
    sections: list[DocSection] = []

    normalized_header = [cell.strip() if cell.strip() else f"column_{index + 1}" for index, cell in enumerate(header)]
    if normalized_header:
        non_empty_counts = {label: 0 for label in normalized_header}
        for row in data_rows:
            for column_index, label in enumerate(normalized_header):
                if column_index < len(row) and row[column_index].strip():
                    non_empty_counts[label] += 1

        summary_lines = [
            f"row_count: {len(data_rows)}",
            f"column_count: {len(normalized_header)}",
        ]
        summary_lines.extend(f"{label}.non_empty_count: {non_empty_counts[label]}" for label in normalized_header)
        sections.append(
            DocSection(
                heading=f"{source_name} / Summary",
                level=1,
                content="\n".join(summary_lines),
            )
        )
        sections.append(
            DocSection(
                heading=f"{source_name} / Columns",
                level=1,
                content=(
                    f"columns: {', '.join(normalized_header)}\n"
                    f"row_count: {len(data_rows)}"
                ),
            )
        )

    for index, row in enumerate(data_rows, start=1):
        cells: list[str] = []
        heading_values: list[str] = []
        for column_index, value in enumerate(row):
            label = normalized_header[column_index] if column_index < len(normalized_header) else f"column_{column_index + 1}"
            cleaned_value = value.strip()
            if cleaned_value:
                cells.append(f"{label}: {cleaned_value}")
                if len(heading_values) < 2:
                    heading_values.append(f"{label}={cleaned_value}")
        if cells:
            heading_suffix = f" - {' | '.join(heading_values)}" if heading_values else ""
            sections.append(DocSection(heading=f"Row {index}{heading_suffix}", level=1, content="\n".join(cells)))

    if sections:
        return sections

    return [DocSection(heading=source_name, level=1, content="\n".join(", ".join(cell.strip() for cell in row if cell.strip()) for row in rows if any(cell.strip() for cell in row)).strip())]


def _load_csv_file(file_path: Path, *, site_id: str, site_name: str) -> DocPage | None:
    with file_path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        rows = list(csv.reader(handle))

    return _build_file_page_with_sections(
        file_path,
        site_id=site_id,
        site_name=site_name,
        title=file_path.name,
        sections=_csv_rows_to_sections(rows, source_name=file_path.name),
    )


def _load_pdf_file(file_path: Path, *, site_id: str, site_name: str) -> DocPage | None:
    from pypdf import PdfReader

    reader = PdfReader(str(file_path))
    sections: list[DocSection] = []
    for index, page in enumerate(reader.pages, start=1):
        extracted = page.extract_text() or ""
        extracted = extracted.strip()
        if extracted:
            sections.append(DocSection(heading=f"Page {index}", level=1, content=extracted))

    return _build_file_page_with_sections(
        file_path,
        site_id=site_id,
        site_name=site_name,
        title=file_path.name,
        sections=sections,
    )


def _load_docx_file(file_path: Path, *, site_id: str, site_name: str) -> DocPage | None:
    from docx import Document

    document = Document(str(file_path))
    sections = _docx_paragraphs_to_sections(document.paragraphs, fallback_heading=file_path.name)
    return _build_file_page_with_sections(
        file_path,
        site_id=site_id,
        site_name=site_name,
        title=file_path.name,
        sections=sections,
    )


def _code_file_to_language(suffix: str) -> str:
    """Map file extension to language name."""
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".sql": "sql",
        ".sh": "bash",
        ".bash": "bash",
        ".rb": "ruby",
        ".php": "php",
        ".cpp": "cpp",
        ".c": "c",
        ".cs": "csharp",
        ".kt": "kotlin",
    }
    return mapping.get(suffix.lower(), "unknown")


def _load_code_file(file_path: Path, *, site_id: str, site_name: str) -> DocPage | None:
    """Load and parse a code file, extracting functions/classes as sections."""
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    cleaned = content.strip()
    if not cleaned:
        return None

    language = _code_file_to_language(file_path.suffix)
    sections: list[DocSection] = []

    # Extract code sections (functions, classes, etc.)
    code_sections = extract_code_sections(content, language)
    if code_sections:
        for code_sec in code_sections:
            sections.append(
                DocSection(
                    heading=f"{code_sec.name} (line {code_sec.start_line + 1})",
                    level=1,
                    content=f"{language.upper()} {code_sec.name}\n{code_sec.signature}",
                )
            )

    # Also include full file content as fallback/context
    if not sections:
        sections = [DocSection(heading=f"{language} code", level=1, content=cleaned)]
    else:
        # Add full file summary section
        lines_count = len(cleaned.split("\n"))
        sections.insert(
            0,
            DocSection(
                heading="File Overview",
                level=1,
                content=f"{file_path.name}\nLanguage: {language}\nLines: {lines_count}\nType: Source code",
            ),
        )

    return _build_file_page_with_sections(
        file_path,
        site_id=site_id,
        site_name=site_name,
        title=file_path.name,
        sections=sections,
    )


def _xlsx_cell_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value)


def _xlsx_rows_to_sections(sheet_rows: list[list[Any]], *, sheet_name: str) -> list[DocSection]:
    normalized_rows = [[_xlsx_cell_to_text(cell) for cell in row] for row in sheet_rows]
    meaningful_rows = [row for row in normalized_rows if any(cell for cell in row)]
    if not meaningful_rows:
        return []

    header = meaningful_rows[0]
    data_rows = meaningful_rows[1:] if any(header) else meaningful_rows
    sections: list[DocSection] = []

    normalized_header = [cell if cell else f"column_{index + 1}" for index, cell in enumerate(header)]
    if normalized_header:
        non_empty_counts = {label: 0 for label in normalized_header}
        for row in data_rows:
            for column_index, label in enumerate(normalized_header):
                if column_index < len(row) and row[column_index]:
                    non_empty_counts[label] += 1

        summary_lines = [
            f"row_count: {len(data_rows)}",
            f"column_count: {len(normalized_header)}",
        ]
        summary_lines.extend(f"{label}.non_empty_count: {non_empty_counts[label]}" for label in normalized_header)
        sections.append(
            DocSection(
                heading=f"{sheet_name} / Summary",
                level=1,
                content="\n".join(summary_lines),
            )
        )
        sections.append(
            DocSection(
                heading=f"{sheet_name} / Columns",
                level=1,
                content=(
                    f"columns: {', '.join(normalized_header)}\n"
                    f"row_count: {len(data_rows)}"
                ),
            )
        )

    for index, row in enumerate(data_rows, start=1):
        cells: list[str] = []
        heading_values: list[str] = []
        for column_index, value in enumerate(row):
            if not value:
                continue
            label = normalized_header[column_index] if column_index < len(normalized_header) else f"column_{column_index + 1}"
            cells.append(f"{label}: {value}")
            if len(heading_values) < 2:
                heading_values.append(f"{label}={value}")
        if cells:
            heading_suffix = f" - {' | '.join(heading_values)}" if heading_values else ""
            sections.append(DocSection(heading=f"{sheet_name} / Row {index}{heading_suffix}", level=1, content="\n".join(cells)))

    if sections:
        return sections

    fallback = "\n".join(" | ".join(cell for cell in row if cell) for row in meaningful_rows if any(cell for cell in row)).strip()
    return [DocSection(heading=sheet_name, level=1, content=fallback)] if fallback else []


def _load_xlsx_file(file_path: Path, *, site_id: str, site_name: str) -> DocPage | None:
    from openpyxl import load_workbook  # type: ignore[import-untyped]

    workbook = load_workbook(filename=str(file_path), read_only=True, data_only=True)
    try:
        sections: list[DocSection] = []
        for sheet in workbook.worksheets:
            rows = [list(row) for row in sheet.iter_rows(values_only=True)]
            sections.extend(_xlsx_rows_to_sections(rows, sheet_name=sheet.title))
    finally:
        workbook.close()

    return _build_file_page_with_sections(
        file_path,
        site_id=site_id,
        site_name=site_name,
        title=file_path.name,
        sections=sections,
    )


def _docx_heading_level(style_name: str) -> int | None:
    match = re.match(r"Heading\s+(\d+)$", style_name.strip(), flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _docx_paragraphs_to_sections(paragraphs: list[Any], *, fallback_heading: str) -> list[DocSection]:
    sections: list[DocSection] = []
    current_heading = fallback_heading
    current_level = 1
    current_parts: list[str] = []

    for paragraph in paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue

        style = getattr(paragraph, "style", None)
        style_name = getattr(style, "name", "") or ""
        heading_level = _docx_heading_level(style_name)
        if heading_level is not None:
            if current_parts:
                sections.append(
                    DocSection(
                        heading=current_heading,
                        level=current_level,
                        content="\n\n".join(current_parts).strip(),
                    )
                )
                current_parts = []
            current_heading = text
            current_level = heading_level
            continue

        current_parts.append(text)

    if current_parts:
        sections.append(
            DocSection(
                heading=current_heading,
                level=current_level,
                content="\n\n".join(current_parts).strip(),
            )
        )

    return sections


def is_supported_remote_source_url(source_url: str) -> bool:
    parsed = urlparse(source_url.strip())
    if parsed.scheme not in {"http", "https"}:
        return False
    return _supported_remote_suffix_from_url(source_url) in SUPPORTED_REMOTE_FILE_EXTENSIONS


def _remote_title(source_url: str) -> str:
    parsed = urlparse(source_url)
    last_segment = Path(parsed.path).name
    direct_suffix = Path(parsed.path).suffix.lower()
    if last_segment and direct_suffix in SUPPORTED_REMOTE_FILE_EXTENSIONS:
        return last_segment

    query = parse_qs(parsed.query)
    for key in ("id", "file", "SourceUrl", "sourceurl"):
        for raw_value in query.get(key, []):
            candidate = unquote(str(raw_value or "")).strip()
            if not candidate:
                continue
            candidate_path = urlparse(candidate).path or candidate
            candidate_name = Path(candidate_path).name
            if Path(candidate_name).suffix.lower() in SUPPORTED_REMOTE_FILE_EXTENSIONS:
                return candidate_name

    return last_segment or source_url


def _detect_remote_file_type(response: httpx.Response) -> str:
    content_type = response.headers.get("content-type", "").lower()
    if "text/csv" in content_type or "application/csv" in content_type or "application/vnd.ms-excel" in content_type:
        return ".csv"
    if "text/markdown" in content_type or "application/markdown" in content_type or "text/x-markdown" in content_type:
        return ".md"
    if "application/pdf" in content_type:
        return ".pdf"
    if (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in content_type
        or "application/msword" in content_type
    ):
        return ".docx"
    if "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in content_type:
        return ".xlsx"
    if "application/json" in content_type or "+json" in content_type:
        return ".json"

    content_disposition = response.headers.get("content-disposition", "")
    match = re.search(r'filename="?([^";]+)"?', content_disposition, flags=re.IGNORECASE)
    if match:
        suffix = Path(match.group(1)).suffix.lower()
        if suffix in SUPPORTED_REMOTE_FILE_EXTENSIONS:
            return suffix

    return _supported_remote_suffix_from_url(str(response.url)) or Path(urlparse(str(response.url)).path).suffix.lower()


def _enforce_remote_size_limit(response: httpx.Response, *, max_bytes: int) -> None:
    content_length = response.headers.get("content-length", "").strip()
    if content_length.isdigit() and int(content_length) > max_bytes:
        raise ValueError(
            f"Remote document is too large ({content_length} bytes). Maximum allowed size is {max_bytes} bytes."
        )

    body_size = len(response.content)
    if body_size > max_bytes:
        raise ValueError(
            f"Remote document is too large after download ({body_size} bytes). Maximum allowed size is {max_bytes} bytes."
        )


def _load_remote_json(response: httpx.Response, *, site_id: str, site_name: str) -> DocPage | None:
    data = response.json()
    title = _remote_title(str(response.url))
    return _build_remote_page_with_sections(
        str(response.url),
        site_id=site_id,
        site_name=site_name,
        title=title,
        sections=_json_to_sections(data, source_name=title),
    )


def _load_remote_csv(response: httpx.Response, *, site_id: str, site_name: str) -> DocPage | None:
    title = _remote_title(str(response.url))
    text = response.text
    rows = list(csv.reader(io.StringIO(text)))
    return _build_remote_page_with_sections(
        str(response.url),
        site_id=site_id,
        site_name=site_name,
        title=title,
        sections=_csv_rows_to_sections(rows, source_name=title),
    )


def _load_remote_markdown(response: httpx.Response, *, site_id: str, site_name: str) -> DocPage | None:
    title = _remote_title(str(response.url))
    return _build_remote_page_with_sections(
        str(response.url),
        site_id=site_id,
        site_name=site_name,
        title=title,
        sections=_markdown_to_sections(response.text, fallback_heading=title),
    )


def _load_remote_pdf(response: httpx.Response, *, site_id: str, site_name: str) -> DocPage | None:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(response.content))
    sections: list[DocSection] = []
    for index, page in enumerate(reader.pages, start=1):
        extracted = page.extract_text() or ""
        extracted = extracted.strip()
        if extracted:
            sections.append(DocSection(heading=f"Page {index}", level=1, content=extracted))

    return _build_remote_page_with_sections(
        str(response.url),
        site_id=site_id,
        site_name=site_name,
        title=_remote_title(str(response.url)),
        sections=sections,
    )


def _load_remote_docx(response: httpx.Response, *, site_id: str, site_name: str) -> DocPage | None:
    from docx import Document

    document = Document(io.BytesIO(response.content))
    title = _remote_title(str(response.url))
    sections = _docx_paragraphs_to_sections(document.paragraphs, fallback_heading=title)
    return _build_remote_page_with_sections(
        str(response.url),
        site_id=site_id,
        site_name=site_name,
        title=title,
        sections=sections,
    )


def _load_remote_xlsx(response: httpx.Response, *, site_id: str, site_name: str) -> DocPage | None:
    from openpyxl import load_workbook

    title = _remote_title(str(response.url))
    workbook = load_workbook(filename=io.BytesIO(response.content), read_only=True, data_only=True)
    try:
        sections: list[DocSection] = []
        for sheet in workbook.worksheets:
            rows = [list(row) for row in sheet.iter_rows(values_only=True)]
            sections.extend(_xlsx_rows_to_sections(rows, sheet_name=sheet.title))
    finally:
        workbook.close()

    return _build_remote_page_with_sections(
        str(response.url),
        site_id=site_id,
        site_name=site_name,
        title=title,
        sections=sections,
    )


LOCAL_FORMAT_PARSER_PLUGINS: tuple[LocalFormatParserPlugin, ...] = (
    LocalFormatParserPlugin(name="csv", suffixes=(".csv",), loader_name="_load_csv_file"),
    LocalFormatParserPlugin(name="markdown", suffixes=(".md", ".markdown"), loader_name="_load_markdown_file"),
    LocalFormatParserPlugin(name="html", suffixes=(".html", ".htm"), loader_name="_load_html_file"),
    LocalFormatParserPlugin(name="json", suffixes=(".json",), loader_name="_load_json_file"),
    LocalFormatParserPlugin(name="pdf", suffixes=(".pdf",), loader_name="_load_pdf_file"),
    LocalFormatParserPlugin(name="word", suffixes=(".docx",), loader_name="_load_docx_file"),
    LocalFormatParserPlugin(name="xlsx", suffixes=(".xlsx",), loader_name="_load_xlsx_file"),
    # Code files
    LocalFormatParserPlugin(
        name="code",
        suffixes=(".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".sql", ".sh", ".bash", ".rb", ".php", ".cpp", ".c", ".cs", ".kt"),
        loader_name="_load_code_file",
    ),
)


REMOTE_FORMAT_PARSER_PLUGINS: tuple[RemoteFormatParserPlugin, ...] = (
    RemoteFormatParserPlugin(name="csv", suffixes=(".csv",), loader_name="_load_remote_csv"),
    RemoteFormatParserPlugin(name="markdown", suffixes=(".md", ".markdown"), loader_name="_load_remote_markdown"),
    RemoteFormatParserPlugin(name="json", suffixes=(".json",), loader_name="_load_remote_json"),
    RemoteFormatParserPlugin(name="pdf", suffixes=(".pdf",), loader_name="_load_remote_pdf"),
    RemoteFormatParserPlugin(name="word", suffixes=(".docx",), loader_name="_load_remote_docx"),
    RemoteFormatParserPlugin(name="xlsx", suffixes=(".xlsx",), loader_name="_load_remote_xlsx"),
)


def _resolve_local_format_parser(suffix: str) -> LocalFormatParserPlugin | None:
    normalized = suffix.lower().strip()
    for plugin in LOCAL_FORMAT_PARSER_PLUGINS:
        if plugin.can_handle(normalized):
            return plugin
    return None


def _resolve_remote_format_parser(suffix: str) -> RemoteFormatParserPlugin | None:
    normalized = suffix.lower().strip()
    for plugin in REMOTE_FORMAT_PARSER_PLUGINS:
        if plugin.can_handle(normalized):
            return plugin
    return None


def load_remote_pages(
    source_url: str,
    *,
    site_id: str,
    site_name: str,
    auth_session: AuthSession | None = None,
    timeout_seconds: float = 20.0,
    max_bytes: int = DEFAULT_MAX_REMOTE_BYTES,
) -> list[DocPage]:
    if max_bytes < 1024:
        raise ValueError("max_bytes must be at least 1024")

    auth_headers = dict((auth_session or {}).get("headers") or {})
    auth_cookies = dict((auth_session or {}).get("cookies") or {})

    with httpx.Client(
        timeout=timeout_seconds,
        follow_redirects=True,
        headers=auth_headers,
        cookies=auth_cookies,
    ) as client:
        response = client.get(source_url)

        if response.status_code in {401, 403}:
            if auth_session:
                raise AuthenticationRequiredError(
                    "Authenticated session could not access this remote document URL. "
                    "Retry interactive SSO or ingest from the site/document-library URL.",
                    login_url=source_url,
                )
            raise AuthenticationRequiredError(
                "Authentication is required to access this remote document URL.",
                login_url=source_url,
            )

        response.raise_for_status()
    _enforce_remote_size_limit(response, max_bytes=max_bytes)

    suffix = _detect_remote_file_type(response)
    parser = _resolve_remote_format_parser(suffix)
    if parser is None:
        raise ValueError("Unsupported remote file type. Supported formats: .csv, .json, .md, .markdown, .pdf, .docx, .xlsx")

    page = parser.parse(response, site_id=site_id, site_name=site_name)

    return [page] if page is not None else []


def load_local_pages(source_path: str | Path, *, site_id: str, site_name: str) -> list[DocPage]:
    path = Path(source_path).expanduser().resolve()
    pages: list[DocPage] = []
    for file_path in _iter_supported_files(path):
        parser = _resolve_local_format_parser(file_path.suffix)
        page = parser.parse(file_path, site_id=site_id, site_name=site_name) if parser is not None else None

        if page is not None:
            pages.append(page)

    return pages