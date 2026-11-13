from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

_TOP_LEVEL_DOC_ENTRYPOINT_SEGMENTS = {
    "intro",
    "introduction",
    "getting-started",
    "quickstart",
    "overview",
    "start",
    "basics",
    "install",
    "installation",
}


@dataclass
class SiteDefinition:
    site_id: str
    site_name: str
    start_url: str
    allowed_host: str
    allowed_path_prefix: str
    start_urls: tuple[str, ...] = ()
    allowed_path_prefixes: tuple[str, ...] = ()

    @property
    def crawl_start_urls(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((self.start_url, *self.start_urls)))

    @property
    def crawl_path_prefixes(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((self.allowed_path_prefix, *self.allowed_path_prefixes)))


def derive_allowed_path_prefix(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "/"
    if len(parts) == 1 and parts[0].lower() in _TOP_LEVEL_DOC_ENTRYPOINT_SEGMENTS:
        return "/"
    return f"/{parts[0]}/"


def score_start_path(path: str) -> int:
    lowered = (path or "/").lower().rstrip("/")
    if not lowered or lowered == "/":
        return -1000

    last_segment = lowered.rsplit("/", 1)[-1]
    preferred = {
        "intro": 120,
        "introduction": 115,
        "getting-started": 110,
        "quickstart": 105,
        "overview": 100,
        "start": 95,
        "basics": 90,
    }
    return preferred.get(last_segment, 0) - lowered.count("/")


def _sanitize_site_id(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "site"


def _normalize_path_prefix(path: str) -> str:
    normalized = "/" + "/".join(part for part in path.split("/") if part)
    return normalized if normalized == "/" else normalized.rstrip("/") + "/"


def _looks_like_file_segment(segment: str) -> bool:
    suffix = Path(segment).suffix.lower()
    return bool(suffix and suffix not in {".aspx", ".html", ".htm"})


def _derive_hosteddocs_allowed_path_prefix(parsed: Any) -> str | None:
    query = parse_qs(parsed.query)
    for key in ("id", "RootFolder"):
        for raw_value in query.get(key) or []:
            decoded = unquote(str(raw_value or "")).strip()
            if not decoded.startswith("/"):
                continue
            candidate = decoded
            if _looks_like_file_segment(candidate.rsplit("/", 1)[-1]):
                candidate = candidate.rsplit("/", 1)[0]
            normalized = _normalize_path_prefix(quote(candidate, safe="/"))
            if normalized != "/":
                return normalized

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0].lower() not in {"sites", "teams", "personal"}:
        return None
    if len(parts) == 2:
        return _normalize_path_prefix(f"/{parts[0]}/{parts[1]}")
    if _looks_like_file_segment(parts[-1]):
        return _normalize_path_prefix("/" + "/".join(parts[:-1]))
    if parts[-1].lower() in {"allitems.aspx", "home.aspx"} and len(parts) >= 4 and parts[-2].lower() == "forms":
        return _normalize_path_prefix("/" + "/".join(parts[:-2]))
    return _normalize_path_prefix(parsed.path)


def _derive_learn_microsoft_allowed_path_prefix(parsed: Any) -> str | None:
    if parsed.netloc.lower() != "learn.microsoft.com":
        return None

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or not re.fullmatch(r"[a-z]{2}-[a-z]{2}", parts[0], flags=re.IGNORECASE):
        return None

    return _normalize_path_prefix("/" + "/".join(parts[:3]))


def site_from_url(url: str) -> SiteDefinition:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url must be an absolute http(s) URL")
    allowed_host = parsed.netloc.lower()
    allowed_path_prefix = (
        _derive_hosteddocs_allowed_path_prefix(parsed)
        or _derive_learn_microsoft_allowed_path_prefix(parsed)
        or derive_allowed_path_prefix(parsed.path)
    )
    identifier = allowed_host if allowed_path_prefix == "/" else f"{allowed_host}-{allowed_path_prefix.strip('/')}"
    return SiteDefinition(
        site_id=_sanitize_site_id(identifier),
        site_name=allowed_host,
        start_url=url.strip(),
        allowed_host=allowed_host,
        allowed_path_prefix=allowed_path_prefix,
    )


def site_from_urls(
    urls: list[str],
    *,
    allowed_url_prefixes: list[str] | None = None,
    site_id: str | None = None,
    site_name: str | None = None,
) -> SiteDefinition:
    cleaned_urls = list(dict.fromkeys(url.strip() for url in urls if url.strip()))
    if not cleaned_urls:
        raise ValueError("urls must contain at least one absolute http(s) URL")
    parsed_urls = [urlparse(url) for url in cleaned_urls]
    if any(parsed.scheme not in {"http", "https"} or not parsed.netloc for parsed in parsed_urls):
        raise ValueError("all start URLs must be absolute http(s) URLs")
    allowed_host = parsed_urls[0].netloc.lower()
    if any(parsed.netloc.lower() != allowed_host for parsed in parsed_urls):
        raise ValueError("all start URLs must use the same host")

    if allowed_url_prefixes is not None:
        raw_prefixes = allowed_url_prefixes
    elif len(cleaned_urls) == 1:
        raw_prefixes = [derive_allowed_path_prefix(parsed_urls[0].path)]
    else:
        raw_prefixes = [parsed.path or "/" for parsed in parsed_urls]

    path_prefixes: list[str] = []
    for raw_prefix in raw_prefixes:
        cleaned_prefix = raw_prefix.strip()
        if not cleaned_prefix:
            continue
        parsed_prefix = urlparse(cleaned_prefix)
        if parsed_prefix.scheme or parsed_prefix.netloc:
            if parsed_prefix.scheme not in {"http", "https"} or parsed_prefix.netloc.lower() != allowed_host:
                raise ValueError("all allowed URL prefixes must use the same host as the start URLs")
            prefix_path = parsed_prefix.path or "/"
        else:
            prefix_path = cleaned_prefix
        path_prefixes.append(_normalize_path_prefix(prefix_path))

    path_prefixes = list(dict.fromkeys(path_prefixes))
    if not path_prefixes:
        raise ValueError("allowed_url_prefixes must contain at least one URL or path prefix")
    normalized_prefixes = tuple(prefix.rstrip("/") or "/" for prefix in path_prefixes)
    for parsed_url in parsed_urls:
        path = parsed_url.path or "/"
        if not any(
            prefix == "/" or path == prefix or path.startswith((prefix + "/", prefix + "."))
            for prefix in normalized_prefixes
        ):
            raise ValueError(f"start URL is outside allowed_url_prefixes: {parsed_url.geturl()}")

    derived_id_parts = [allowed_host, *(prefix.rstrip("/").rsplit("/", 1)[-1] for prefix in path_prefixes)]
    return SiteDefinition(
        site_id=_sanitize_site_id(site_id or "-".join(derived_id_parts)),
        site_name=site_name.strip() if site_name and site_name.strip() else allowed_host,
        start_url=cleaned_urls[0],
        allowed_host=allowed_host,
        allowed_path_prefix=path_prefixes[0],
        start_urls=tuple(cleaned_urls),
        allowed_path_prefixes=tuple(path_prefixes),
    )


def site_from_local_path(path: str) -> SiteDefinition:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Local source not found: {resolved}")
    base_name = resolved.stem if resolved.is_file() else resolved.name
    site_name = resolved.name if resolved.is_file() else resolved.as_posix()
    fingerprint = hashlib.sha1(resolved.as_posix().lower().encode()).hexdigest()[:8]
    return SiteDefinition(
        site_id=_sanitize_site_id(f"local-{base_name}-{fingerprint}"),
        site_name=site_name,
        start_url=str(resolved),
        allowed_host="local",
        allowed_path_prefix="/",
    )


def site_from_latest_job(jobs: dict[str, Any], site_id: str) -> SiteDefinition | None:
    matching = [job for job in jobs.values() if job.site_id == site_id]
    if not matching:
        return None

    latest = max(matching, key=lambda job: (job.started_at or "", job.created_at))
    return SiteDefinition(
        site_id=latest.site_id,
        site_name=latest.site_name,
        start_url=latest.start_url,
        allowed_host=latest.allowed_host,
        allowed_path_prefix=latest.allowed_path_prefix,
        start_urls=latest.start_urls,
        allowed_path_prefixes=latest.allowed_path_prefixes,
    )


def site_from_topic_routes(routes: dict[str, Any], site_id: str) -> SiteDefinition | None:
    matching = [
        (route, reference)
        for route in routes.values()
        for reference in route.routed_sites
        if reference.site_id == site_id
    ]
    if not matching:
        return None

    _, reference = max(matching, key=lambda item: item[0].updated_at)
    parsed = urlparse(reference.start_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    allowed_path_prefixes = reference.allowed_path_prefixes or (derive_allowed_path_prefix(parsed.path),)
    if allowed_path_prefixes == ("/",):
        allowed_path_prefixes = (derive_allowed_path_prefix(parsed.path),)
    start_urls = reference.start_urls or (reference.start_url,)
    return SiteDefinition(
        site_id=reference.site_id,
        site_name=reference.site_name,
        start_url=reference.start_url,
        allowed_host=parsed.netloc.lower(),
        allowed_path_prefix=allowed_path_prefixes[0],
        start_urls=start_urls,
        allowed_path_prefixes=allowed_path_prefixes,
    )


def site_from_indexed_metadatas(metadatas: list[Any], site_id: str) -> SiteDefinition | None:
    site_name = site_id
    source_urls: list[str] = []
    for meta in metadatas:
        if not isinstance(meta, dict):
            continue
        maybe_name = str(meta.get("site_name", "")).strip()
        maybe_url = str(meta.get("source_url", "")).strip()
        if maybe_name:
            site_name = maybe_name
        if maybe_url:
            source_urls.append(maybe_url)

    valid_urls = []
    for url in dict.fromkeys(source_urls):
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            valid_urls.append(url)
    if not valid_urls:
        return None

    start_url = max(valid_urls, key=lambda value: score_start_path(urlparse(value).path))
    parsed = urlparse(start_url)
    return SiteDefinition(
        site_id=site_id,
        site_name=site_name,
        start_url=start_url,
        allowed_host=parsed.netloc.lower(),
        allowed_path_prefix=derive_allowed_path_prefix(parsed.path),
    )
