from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..ingest.service import IngestRunResult
from ..routing import normalize_topic

ACTIVE_JOB_STATUSES = {"queued", "running"}


@dataclass
class IngestJobRecord:
    job_id: str
    site_id: str
    site_name: str
    start_url: str
    allowed_host: str
    allowed_path_prefix: str
    status: str
    phase: str
    created_at: str
    incremental: bool
    max_pages: int
    delay: float
    progress_percent: int = 0
    pages_kept: int = 0
    visited_urls: int = 0
    queued_urls: int = 0
    index_done: int = 0
    index_total: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    needs_authentication: bool = False
    detected_login_url: str | None = None
    start_urls: tuple[str, ...] = ()
    allowed_path_prefixes: tuple[str, ...] = ()


@dataclass
class TopicSiteReference:
    site_id: str
    site_name: str
    start_url: str
    start_urls: tuple[str, ...] = ()
    allowed_path_prefixes: tuple[str, ...] = ()


@dataclass
class TopicRouteRecord:
    topic: str
    topic_key: str
    site_id: str
    site_name: str
    start_url: str
    created_at: str
    updated_at: str
    start_urls: tuple[str, ...] = ()
    allowed_path_prefixes: tuple[str, ...] = ()
    sites: tuple[TopicSiteReference, ...] = ()

    @property
    def routed_sites(self) -> tuple[TopicSiteReference, ...]:
        if self.sites:
            return self.sites
        return (
            TopicSiteReference(
                site_id=self.site_id,
                site_name=self.site_name,
                start_url=self.start_url,
                start_urls=self.start_urls or (self.start_url,),
                allowed_path_prefixes=self.allowed_path_prefixes or ("/",),
            ),
        )

    @property
    def site_ids(self) -> tuple[str, ...]:
        return tuple(reference.site_id for reference in self.routed_sites)

    def with_sites(
        self,
        sites: tuple[TopicSiteReference, ...],
        *,
        updated_at: str,
    ) -> TopicRouteRecord:
        if not sites:
            raise ValueError("sites must contain at least one topic site reference")
        primary = sites[0]
        return TopicRouteRecord(
            topic=self.topic,
            topic_key=self.topic_key,
            site_id=primary.site_id,
            site_name=primary.site_name,
            start_url=primary.start_url,
            created_at=self.created_at,
            updated_at=updated_at,
            start_urls=primary.start_urls,
            allowed_path_prefixes=primary.allowed_path_prefixes,
            sites=sites,
        )


@dataclass
class SiteSyncRecord:
    site_id: str
    site_name: str
    start_url: str
    allowed_host: str
    allowed_path_prefix: str
    last_job_id: str | None = None
    last_status: str | None = None
    last_scrape_started_at: str | None = None
    last_scrape_finished_at: str | None = None
    last_successful_scrape_at: str | None = None
    last_indexed_at: str | None = None
    last_pages_scraped: int | None = None
    last_indexed_chunks: int | None = None
    last_error: str | None = None
    updated_at: str | None = None
    start_urls: tuple[str, ...] = ()
    allowed_path_prefixes: tuple[str, ...] = ()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _format_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _result_to_dict(result: IngestRunResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["duration_seconds"] = round(float(payload["duration_seconds"]), 3)
    return payload


_normalize_topic = normalize_topic


def _string_tuple(value: Any, fallback: str) -> tuple[str, ...]:
    if isinstance(value, list):
        cleaned = tuple(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))
        if cleaned:
            return cleaned
    return (fallback,)


def _job_to_dict(job: IngestJobRecord) -> dict[str, Any]:
    payload = asdict(job)
    if isinstance(job.result, dict):
        for key in (
            "pages_scraped",
            "indexed_chunks",
            "changed_pages",
            "removed_pages",
            "skipped_pages",
            "duration_seconds",
        ):
            if key in job.result and key not in payload:
                payload[key] = job.result[key]
    return payload


def _job_from_dict(raw: dict[str, Any]) -> IngestJobRecord | None:
    try:
        start_url = str(raw["start_url"])
        allowed_path_prefix = str(raw["allowed_path_prefix"])
        return IngestJobRecord(
            job_id=str(raw["job_id"]),
            site_id=str(raw["site_id"]),
            site_name=str(raw.get("site_name", raw["site_id"])),
            start_url=start_url,
            allowed_host=str(raw["allowed_host"]),
            allowed_path_prefix=allowed_path_prefix,
            status=str(raw.get("status", "failed")),
            phase=str(raw.get("phase", "failed")),
            created_at=str(raw.get("created_at", _now_iso())),
            incremental=bool(raw.get("incremental", True)),
            max_pages=int(raw.get("max_pages", 1200)),
            delay=float(raw.get("delay", 0.2)),
            progress_percent=int(raw.get("progress_percent", 0)),
            pages_kept=int(raw.get("pages_kept", 0)),
            visited_urls=int(raw.get("visited_urls", 0)),
            queued_urls=int(raw.get("queued_urls", 0)),
            index_done=int(raw.get("index_done", 0)),
            index_total=int(raw.get("index_total", 0)),
            started_at=str(raw["started_at"]) if raw.get("started_at") else None,
            finished_at=str(raw["finished_at"]) if raw.get("finished_at") else None,
            result=raw.get("result") if isinstance(raw.get("result"), dict) else None,
            error=str(raw["error"]) if raw.get("error") else None,
            needs_authentication=bool(raw.get("needs_authentication", False)),
            detected_login_url=(str(raw["detected_login_url"]) if raw.get("detected_login_url") else None),
            start_urls=_string_tuple(raw.get("start_urls"), start_url),
            allowed_path_prefixes=_string_tuple(raw.get("allowed_path_prefixes"), allowed_path_prefix),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _read_jobs_state(state_path: Path) -> dict[str, IngestJobRecord]:
    if not state_path.exists():
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw_jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    if not isinstance(raw_jobs, list):
        return {}

    jobs: dict[str, IngestJobRecord] = {}
    for item in raw_jobs:
        if not isinstance(item, dict):
            continue
        job = _job_from_dict(item)
        if job is not None:
            jobs[job.job_id] = job

    restarted_at = _now_iso()
    for job in jobs.values():
        if job.status in ACTIVE_JOB_STATUSES:
            job.status = "failed"
            job.phase = "failed"
            job.finished_at = restarted_at
            restart_error = "Ingestion was interrupted because the server restarted."
            job.error = f"{job.error}; {restart_error}" if job.error else restart_error

    return jobs


def _atomic_write_json_with_retries(
    state_path: Path,
    payload: dict[str, Any],
    *,
    retries: int = 10,
    base_delay_seconds: float = 0.05,
) -> None:
    """Write JSON atomically with retries on Windows PermissionError (WinError 5)."""
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    last_error: PermissionError | None = None

    for attempt in range(retries):
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=str(state_path.parent),
            prefix=f"{state_path.name}.",
            suffix=".tmp",
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        try:
            temp_path.replace(state_path)
            return
        except PermissionError as exc:
            last_error = exc
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            time.sleep(base_delay_seconds * (attempt + 1))
        except OSError:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    if last_error is not None:
        raise last_error


def _write_jobs_state(state_path: Path, jobs: dict[str, IngestJobRecord]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "jobs": [_job_to_dict(job) for job in sorted(jobs.values(), key=lambda entry: entry.created_at)],
    }
    _atomic_write_json_with_retries(state_path, payload)


def _route_to_dict(route: TopicRouteRecord) -> dict[str, Any]:
    return {
        "topic": route.topic,
        "topic_key": route.topic_key,
        "created_at": route.created_at,
        "updated_at": route.updated_at,
        "sites": [asdict(reference) for reference in route.routed_sites],
    }


def _topic_site_reference_from_dict(raw: dict[str, Any]) -> TopicSiteReference | None:
    site_id = str(raw.get("site_id", "")).strip()
    start_url = str(raw.get("start_url", "")).strip()
    if not site_id or not start_url:
        return None
    return TopicSiteReference(
        site_id=site_id,
        site_name=str(raw.get("site_name", site_id)),
        start_url=start_url,
        start_urls=_string_tuple(raw.get("start_urls"), start_url),
        allowed_path_prefixes=_string_tuple(raw.get("allowed_path_prefixes"), "/"),
    )


def _route_from_dict(raw: dict[str, Any]) -> TopicRouteRecord | None:
    try:
        topic = str(raw["topic"]).strip()
        topic_key = str(raw.get("topic_key", _normalize_topic(topic))).strip()
        if not topic or not topic_key:
            return None
        references: list[TopicSiteReference] = []
        raw_sites = raw.get("sites")
        if isinstance(raw_sites, list):
            for raw_site in raw_sites:
                if isinstance(raw_site, dict):
                    reference = _topic_site_reference_from_dict(raw_site)
                    if reference is not None and reference.site_id not in {item.site_id for item in references}:
                        references.append(reference)

        if not references:
            legacy_reference = _topic_site_reference_from_dict(raw)
            if legacy_reference is not None:
                references.append(legacy_reference)
        if not references:
            return None

        primary = references[0]
        return TopicRouteRecord(
            topic=topic,
            topic_key=topic_key,
            site_id=primary.site_id,
            site_name=primary.site_name,
            start_url=primary.start_url,
            created_at=str(raw.get("created_at", _now_iso())),
            updated_at=str(raw.get("updated_at", _now_iso())),
            start_urls=primary.start_urls,
            allowed_path_prefixes=primary.allowed_path_prefixes,
            sites=tuple(references),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _read_topic_routes_state(state_path: Path) -> dict[str, TopicRouteRecord]:
    if not state_path.exists():
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    raw_routes = payload.get("routes", []) if isinstance(payload, dict) else []
    if not isinstance(raw_routes, list):
        return {}

    routes: dict[str, TopicRouteRecord] = {}
    for item in raw_routes:
        if not isinstance(item, dict):
            continue
        route = _route_from_dict(item)
        if route is not None:
            routes[route.topic_key] = route
    return routes


def _write_topic_routes_state(state_path: Path, routes: dict[str, TopicRouteRecord]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 3,
        "routes": [_route_to_dict(route) for route in sorted(routes.values(), key=lambda entry: entry.topic_key)],
    }
    _atomic_write_json_with_retries(state_path, payload)


def _sync_to_dict(sync: SiteSyncRecord) -> dict[str, Any]:
    return asdict(sync)


def _sync_from_dict(raw: dict[str, Any]) -> SiteSyncRecord | None:
    try:
        site_id = str(raw["site_id"]).strip()
        if not site_id:
            return None
        start_url = str(raw.get("start_url", ""))
        allowed_path_prefix = str(raw.get("allowed_path_prefix", "/"))
        return SiteSyncRecord(
            site_id=site_id,
            site_name=str(raw.get("site_name", site_id)),
            start_url=start_url,
            allowed_host=str(raw.get("allowed_host", "")),
            allowed_path_prefix=allowed_path_prefix,
            last_job_id=str(raw["last_job_id"]) if raw.get("last_job_id") else None,
            last_status=str(raw["last_status"]) if raw.get("last_status") else None,
            last_scrape_started_at=str(raw["last_scrape_started_at"]) if raw.get("last_scrape_started_at") else None,
            last_scrape_finished_at=str(raw["last_scrape_finished_at"]) if raw.get("last_scrape_finished_at") else None,
            last_successful_scrape_at=(
                str(raw["last_successful_scrape_at"]) if raw.get("last_successful_scrape_at") else None
            ),
            last_indexed_at=str(raw["last_indexed_at"]) if raw.get("last_indexed_at") else None,
            last_pages_scraped=int(raw["last_pages_scraped"]) if raw.get("last_pages_scraped") is not None else None,
            last_indexed_chunks=(
                int(raw["last_indexed_chunks"]) if raw.get("last_indexed_chunks") is not None else None
            ),
            last_error=str(raw["last_error"]) if raw.get("last_error") else None,
            updated_at=str(raw["updated_at"]) if raw.get("updated_at") else None,
            start_urls=_string_tuple(raw.get("start_urls"), start_url),
            allowed_path_prefixes=_string_tuple(raw.get("allowed_path_prefixes"), allowed_path_prefix),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _read_site_sync_state(state_path: Path) -> dict[str, SiteSyncRecord]:
    if not state_path.exists():
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    raw_sites = payload.get("sites", []) if isinstance(payload, dict) else []
    if not isinstance(raw_sites, list):
        return {}

    sites: dict[str, SiteSyncRecord] = {}
    for item in raw_sites:
        if not isinstance(item, dict):
            continue
        sync = _sync_from_dict(item)
        if sync is not None:
            sites[sync.site_id] = sync
    return sites


def _write_site_sync_state(state_path: Path, sites: dict[str, SiteSyncRecord]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "sites": [_sync_to_dict(site) for site in sorted(sites.values(), key=lambda entry: entry.site_id)],
    }
    _atomic_write_json_with_retries(state_path, payload)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _sync_staleness_seconds(sync: SiteSyncRecord, now: datetime | None = None) -> int | None:
    now_dt = now or datetime.now(UTC)
    reference = (
        sync.last_successful_scrape_at
        or sync.last_scrape_finished_at
        or sync.last_scrape_started_at
        or sync.updated_at
    )
    reference_dt = _parse_iso_datetime(reference)
    if reference_dt is None:
        return None
    return max(0, int((now_dt - reference_dt).total_seconds()))


def _rank_sync_records(
    records: list[SiteSyncRecord],
    *,
    sort_by: str,
    descending: bool,
    now: datetime | None = None,
) -> list[SiteSyncRecord]:
    now_dt = now or datetime.now(UTC)
    epoch = datetime.fromtimestamp(0, tz=UTC)

    key_fn: Callable[[SiteSyncRecord], float | str | datetime]
    if sort_by == "staleness":
        # Unknown timestamp is treated as highest priority for refresh.
        def staleness_key(record: SiteSyncRecord) -> float:
            staleness = _sync_staleness_seconds(record, now_dt)
            if staleness is None:
                return float("inf")
            return float(staleness)

        key_fn = staleness_key

    elif sort_by == "site_id":
        def site_id_key(record: SiteSyncRecord) -> str:
            return record.site_id

        key_fn = site_id_key

    elif sort_by == "updated_at":
        def updated_at_key(record: SiteSyncRecord) -> datetime:
            return _parse_iso_datetime(record.updated_at) or epoch

        key_fn = updated_at_key

    elif sort_by == "last_successful_scrape_at":
        def last_successful_scrape_key(record: SiteSyncRecord) -> datetime:
            return _parse_iso_datetime(record.last_successful_scrape_at) or epoch

        key_fn = last_successful_scrape_key
    else:
        raise ValueError("sort_by must be one of: staleness, site_id, updated_at, last_successful_scrape_at")

    return sorted(records, key=key_fn, reverse=descending)
