from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def validate_ingest_start_url(
    url: str,
    *,
    refine_doc_start_url: Callable[[str], str],
    http_client_factory: Callable[..., Any],
) -> dict[str, Any] | None:
    try:
        with http_client_factory(timeout=10.0, follow_redirects=True) as client:
            response = client.get(url)
    except Exception:  # noqa: BLE001 - failed probes do not prevent the real ingest attempt
        return None

    if response.status_code != 404:
        return None

    suggested_start_url = refine_doc_start_url(url)
    payload: dict[str, Any] = {
        "status": "invalid_start_url",
        "error_code": "url_not_found_404",
        "url": url,
        "http_status": response.status_code,
        "message": (
            "Provided URL returned HTTP 404. Please provide a valid URL that points to the first page of the "
            "documentation (for example .../docs/intro), not the documentation root/home URL."
        ),
    }
    if suggested_start_url and suggested_start_url != url:
        payload["suggested_start_url"] = suggested_start_url
    return payload


def is_likely_http_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def looks_like_local_path(value: str) -> bool:
    cleaned = value.strip()
    if not cleaned:
        return False
    if cleaned.startswith(("./", ".\\", "../", "..\\", "~/", "~\\", "/", "\\\\")):
        return True
    if re.match(r"^[a-zA-Z]:[\\/]", cleaned):
        return True
    return any(separator in cleaned for separator in ("/", "\\"))


def _path_kind(value: str) -> str:
    cleaned = value.strip()
    if re.match(r"^[a-zA-Z]:[\\/]", cleaned) or cleaned.startswith(("/", "\\\\")):
        return "absolute"
    return "relative"


def resolve_existing_local_path(value: str) -> Path | None:
    candidate = Path(value.strip()).expanduser()
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    return resolved if resolved.exists() else None


def classify_ingest_input(value: str) -> dict[str, Any]:
    cleaned_value = value.strip()
    if not cleaned_value:
        raise ValueError("url must be a non-empty string")
    if is_likely_http_url(cleaned_value):
        return {"input_kind": "url", "url": cleaned_value}

    local_path = resolve_existing_local_path(cleaned_value)
    if local_path is not None:
        return {
            "input_kind": "local_path",
            "path": str(local_path),
            "path_kind": _path_kind(cleaned_value),
            "exists": True,
        }
    if looks_like_local_path(cleaned_value):
        return {
            "input_kind": "local_path",
            "path": cleaned_value,
            "path_kind": _path_kind(cleaned_value),
            "exists": False,
        }
    return {"input_kind": "query", "query": cleaned_value}


def resolve_ingest_input(
    value: str,
    *,
    search_doc_urls_on_web: Callable[[str, int], list[dict[str, str]]],
    max_suggestions: int = 5,
) -> dict[str, Any]:
    classified = classify_ingest_input(value)
    input_kind = str(classified["input_kind"])
    if input_kind == "url":
        return {"status": "resolved_url", "input_kind": "url", "url": str(classified["url"])}
    if input_kind == "local_path" and bool(classified.get("exists", False)):
        return {
            "status": "resolved_local_path",
            "input_kind": "local_path",
            "path": str(classified["path"]),
            "path_kind": str(classified.get("path_kind", "relative")),
        }
    if input_kind == "local_path":
        path_kind = str(classified.get("path_kind", "relative"))
        path_value = str(classified["path"])
        return {
            "status": "invalid_local_path",
            "input_kind": "local_path",
            "path": path_value,
            "path_kind": path_kind,
            "message": (
                f"Provided {path_kind} local path does not exist. "
                "Provide an existing local file/folder path or an HTTP(S) documentation URL."
            ),
        }

    cleaned_value = str(classified["query"])
    suggestions = search_doc_urls_on_web(cleaned_value, max_suggestions)
    if not suggestions:
        return {
            "status": "no_suggestion",
            "query": cleaned_value,
            "message": (
                "No documentation URL suggestion found for this query. "
                "Provide an official documentation URL or call suggest_documentation_urls(topic)."
            ),
        }
    if len(suggestions) > 1:
        return {
            "status": "needs_confirmation",
            "query": cleaned_value,
            "suggestions": suggestions,
            "message": "Multiple documentation URL candidates found. Pick one URL and call ingest(url=<chosen_url>).",
        }

    selected = suggestions[0]
    return {
        "status": "resolved_url",
        "input_kind": "query",
        "query": cleaned_value,
        "url": selected["url"],
        "selected_suggestion": selected,
    }
