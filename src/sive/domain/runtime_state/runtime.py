from __future__ import annotations

import asyncio
import threading
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from chromadb import Collection
    from mcp.server.mcpserver import Context
else:
    Context = Any

from ...domain.auth.session import AuthConfig, AuthenticationRequiredError, AuthSession, capture_authenticated_session
from ...domain.core.sites import (
    SiteDefinition,
    site_from_indexed_metadatas,
    site_from_latest_job,
    site_from_topic_routes,
)
from ...infra.web.scraper import CrawlProgress
from ..ingest.service import run_ingest_for_site
from .progress import format_progress_bar
from .state import (
    ACTIVE_JOB_STATUSES,
    IngestJobRecord,
    SiteSyncRecord,
    TopicRouteRecord,
    TopicSiteReference,
    _job_to_dict,
    _now_iso,
    _read_jobs_state,
    _read_site_sync_state,
    _read_topic_routes_state,
    _result_to_dict,
    _write_jobs_state,
    _write_site_sync_state,
    _write_topic_routes_state,
)


def _site_from_indexed_metadata(collection: Collection, site_id: str) -> SiteDefinition | None:
    try:
        result = collection.get(where={"site_id": site_id}, include=["metadatas"])
    except (AttributeError, TypeError, ValueError):
        return None

    if not isinstance(result, dict):
        return None

    metas = result.get("metadatas", [])
    if not isinstance(metas, list):
        return None

    return site_from_indexed_metadatas(metas, site_id)


def _format_progress_message(job: IngestJobRecord) -> str:
    bar = format_progress_bar(job.progress_percent)
    return (
        f"{bar} phase={job.phase} visited={job.visited_urls} "
        f"kept={job.pages_kept} queued={job.queued_urls}"
    )


def _estimate_crawl_progress(visited: int, queued: int, max_pages: int) -> int:
    safe_visited = max(0, visited)
    if safe_visited == 0:
        return 0

    safe_queued = max(0, queued)
    discovered_total = max(1, safe_visited + safe_queued)
    queue_ratio = safe_visited / discovered_total
    page_limit_ratio = safe_visited / max(1, max_pages)
    crawl_ratio = min(1.0, max(queue_ratio, page_limit_ratio))
    return max(1, min(90, int(crawl_ratio * 90)))



async def _ctx_info_safe(ctx: Context | None, message: str) -> None:
    if ctx is None:
        return
    try:
        await ctx.info(message)
    except ValueError:
        return


async def _ctx_progress_safe(ctx: Context | None, progress: float, total: float, message: str) -> None:
    if ctx is None:
        return
    try:
        await ctx.report_progress(progress, total, message=message)
    except ValueError:
        return
class IngestRuntime:
    def __init__(
        self,
        *,
        collection: Collection,
        jobs_state_path: Path,
        routes_state_path: Path,
        sync_state_path: Path,
        collection_name: str,
        embedding_model_name: str,
    ) -> None:
        self.collection = collection
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model_name

        self.jobs_state_path = jobs_state_path
        self.routes_state_path = routes_state_path
        self.sync_state_path = sync_state_path

        self.jobs_lock = threading.Lock()
        self.routes_lock = threading.Lock()
        self.sync_lock = threading.Lock()

        self.jobs = _read_jobs_state(self.jobs_state_path)
        self.routes = _read_topic_routes_state(self.routes_state_path)
        self.site_sync = _read_site_sync_state(self.sync_state_path)
        self._job_auth_session: dict[str, AuthSession] = {}

        with self.jobs_lock:
            self._persist_jobs_locked()
        with self.routes_lock:
            self._persist_routes_locked()
        with self.sync_lock:
            self._persist_sync_locked()

    def _persist_jobs_locked(self) -> None:
        _write_jobs_state(self.jobs_state_path, self.jobs)

    def _persist_routes_locked(self) -> None:
        _write_topic_routes_state(self.routes_state_path, self.routes)

    def _persist_sync_locked(self) -> None:
        _write_site_sync_state(self.sync_state_path, self.site_sync)

    def active_site_ids(self) -> set[str]:
        with self.jobs_lock:
            return {job.site_id for job in self.jobs.values() if job.status in ACTIVE_JOB_STATUSES}

    def active_jobs_for_site(self, site_id: str) -> list[IngestJobRecord]:
        with self.jobs_lock:
            return [job for job in self.jobs.values() if job.site_id == site_id and job.status in ACTIVE_JOB_STATUSES]

    def active_job_site_ids(self) -> set[str]:
        with self.jobs_lock:
            return {job.site_id for job in self.jobs.values() if job.status in ACTIVE_JOB_STATUSES}

    def get_sync(self, site_id: str) -> SiteSyncRecord | None:
        with self.sync_lock:
            return self.site_sync.get(site_id)

    def list_sync_records(self) -> list[SiteSyncRecord]:
        with self.sync_lock:
            return list(self.site_sync.values())

    def remove_site_state(self, site_id: str) -> dict[str, Any]:
        """Remove persisted runtime state for a documentation site.

        Guardrail: active jobs prevent deletion to avoid inconsistent state.
        """
        cleaned_site_id = site_id.strip()
        if not cleaned_site_id:
            raise ValueError("site_id must be a non-empty string")

        with self.jobs_lock:
            active_job_ids = [
                job.job_id
                for job in self.jobs.values()
                if job.site_id == cleaned_site_id and job.status in ACTIVE_JOB_STATUSES
            ]
            if active_job_ids:
                return {
                    "status": "busy",
                    "site_id": cleaned_site_id,
                    "active_job_ids": active_job_ids,
                }

            job_ids_to_delete = [job_id for job_id, job in self.jobs.items() if job.site_id == cleaned_site_id]
            for job_id in job_ids_to_delete:
                del self.jobs[job_id]
            if job_ids_to_delete:
                self._persist_jobs_locked()

        with self.routes_lock:
            affected_route_keys: list[str] = []
            for route_key, route in list(self.routes.items()):
                remaining_sites = tuple(
                    reference
                    for reference in route.routed_sites
                    if reference.site_id != cleaned_site_id
                )
                if len(remaining_sites) == len(route.routed_sites):
                    continue
                affected_route_keys.append(route_key)
                if remaining_sites:
                    self.routes[route_key] = route.with_sites(remaining_sites, updated_at=_now_iso())
                else:
                    del self.routes[route_key]
            if affected_route_keys:
                self._persist_routes_locked()

        with self.sync_lock:
            had_sync = cleaned_site_id in self.site_sync
            if had_sync:
                del self.site_sync[cleaned_site_id]
                self._persist_sync_locked()

        return {
            "status": "ok",
            "site_id": cleaned_site_id,
            "deleted_jobs": len(job_ids_to_delete),
            "deleted_routes": len(affected_route_keys),
            "deleted_sync": had_sync,
        }

    def update_topic_route(self, *, topic: str, topic_key: str, site: SiteDefinition) -> None:
        now = _now_iso()
        with self.routes_lock:
            previous = self.routes.get(topic_key)
            reference = TopicSiteReference(
                site_id=site.site_id,
                site_name=site.site_name,
                start_url=site.start_url,
                start_urls=site.crawl_start_urls,
                allowed_path_prefixes=site.crawl_path_prefixes,
            )
            references = list(previous.routed_sites if previous else ())
            for index, existing in enumerate(references):
                if existing.site_id == site.site_id:
                    references[index] = reference
                    break
            else:
                references.append(reference)

            primary = references[0]
            self.routes[topic_key] = TopicRouteRecord(
                topic=topic,
                topic_key=topic_key,
                site_id=primary.site_id,
                site_name=primary.site_name,
                start_url=primary.start_url,
                created_at=previous.created_at if previous else now,
                updated_at=now,
                start_urls=primary.start_urls,
                allowed_path_prefixes=primary.allowed_path_prefixes,
                sites=tuple(references),
            )
            self._persist_routes_locked()

    def find_best_topic_route(self, *, query: str, topic: str | None, finder: Any) -> TopicRouteRecord | None:
        with self.routes_lock:
            return finder(self.routes, query=query, topic=topic)

    def resolve_existing_site(self, site_id: str) -> SiteDefinition | None:
        with self.jobs_lock:
            from_jobs = site_from_latest_job(self.jobs, site_id)
        if from_jobs is not None:
            return from_jobs

        with self.routes_lock:
            from_routes = site_from_topic_routes(self.routes, site_id)
        if from_routes is not None:
            return from_routes

        return _site_from_indexed_metadata(self.collection, site_id)

    def _get_or_create_sync_locked(self, site: SiteDefinition) -> SiteSyncRecord:
        existing = self.site_sync.get(site.site_id)
        if existing is not None:
            if site.site_name:
                existing.site_name = site.site_name
            if site.start_url:
                existing.start_url = site.start_url
            if site.allowed_host:
                existing.allowed_host = site.allowed_host
            if site.allowed_path_prefix:
                existing.allowed_path_prefix = site.allowed_path_prefix
            if site.crawl_start_urls:
                existing.start_urls = site.crawl_start_urls
            if site.crawl_path_prefixes:
                existing.allowed_path_prefixes = site.crawl_path_prefixes
            return existing

        created = SiteSyncRecord(
            site_id=site.site_id,
            site_name=site.site_name,
            start_url=site.start_url,
            allowed_host=site.allowed_host,
            allowed_path_prefix=site.allowed_path_prefix,
            updated_at=_now_iso(),
            start_urls=site.crawl_start_urls,
            allowed_path_prefixes=site.crawl_path_prefixes,
        )
        self.site_sync[site.site_id] = created
        return created

    def enqueue_ingest_job(self, site: SiteDefinition, *, incremental: bool, max_pages: int, delay: float) -> dict[str, Any]:
        with self.jobs_lock:
            for existing in self.jobs.values():
                if existing.site_id == site.site_id and existing.status in ACTIVE_JOB_STATUSES:
                    return {
                        "status": "already_running",
                        "site_id": site.site_id,
                        "job_id": existing.job_id,
                        "message": "An ingestion job is already running for this site.",
                    }

            job_id = str(uuid.uuid4())
            job = IngestJobRecord(
                job_id=job_id,
                site_id=site.site_id,
                site_name=site.site_name,
                start_url=site.start_url,
                allowed_host=site.allowed_host,
                allowed_path_prefix=site.allowed_path_prefix,
                status="queued",
                phase="queued",
                created_at=_now_iso(),
                incremental=incremental,
                max_pages=max_pages,
                delay=delay,
                progress_percent=0,
                pages_kept=0,
                visited_urls=0,
                queued_urls=0,
                index_done=0,
                index_total=0,
                needs_authentication=False,
                detected_login_url=None,
                start_urls=site.crawl_start_urls,
                allowed_path_prefixes=site.crawl_path_prefixes,
            )
            self.jobs[job_id] = job
            self._persist_jobs_locked()

        with self.sync_lock:
            sync = self._get_or_create_sync_locked(site)
            sync.last_job_id = job_id
            sync.last_status = "queued"
            sync.last_error = None
            sync.updated_at = _now_iso()
            self._persist_sync_locked()

        thread = threading.Thread(target=self._run_ingest_job, args=(job_id,), daemon=True)
        thread.start()

        return {
            "status": "queued",
            "job_id": job_id,
            "site_id": site.site_id,
            "site_name": site.site_name,
            "start_url": site.start_url,
            "start_urls": list(site.crawl_start_urls),
            "allowed_host": site.allowed_host,
            "allowed_path_prefix": site.allowed_path_prefix,
            "allowed_path_prefixes": list(site.crawl_path_prefixes),
            "message": "Ingestion started asynchronously. Poll ingest_status(job_id) for updates.",
        }

    def _run_ingest_job(self, job_id: str) -> None:
        with self.jobs_lock:
            job = self.jobs.get(job_id)
            if job is None:
                return
            job.status = "running"
            job.phase = "crawl"
            job.progress_percent = 0
            job.pages_kept = 0
            job.visited_urls = 0
            job.queued_urls = 0
            job.index_done = 0
            job.index_total = 0
            job.needs_authentication = False
            job.detected_login_url = None
            job.started_at = _now_iso()
            self._persist_jobs_locked()

        with self.sync_lock:
            site = SiteDefinition(
                site_id=job.site_id,
                site_name=job.site_name,
                start_url=job.start_url,
                allowed_host=job.allowed_host,
                allowed_path_prefix=job.allowed_path_prefix,
                start_urls=job.start_urls,
                allowed_path_prefixes=job.allowed_path_prefixes,
            )
            sync = self._get_or_create_sync_locked(site)
            sync.last_job_id = job_id
            sync.last_status = "running"
            sync.last_scrape_started_at = job.started_at
            sync.updated_at = _now_iso()
            self._persist_sync_locked()

        def _on_progress(progress: CrawlProgress) -> None:
            with self.jobs_lock:
                stored = self.jobs.get(job_id)
                if stored is None or stored.status not in ACTIVE_JOB_STATUSES:
                    return

                phase = str(progress.get("phase", stored.phase))
                visited = int(progress.get("visited", stored.visited_urls))
                queued = int(progress.get("queued", stored.queued_urls))
                pages_kept = int(progress.get("pages_kept", stored.pages_kept))

                stored.phase = phase
                stored.visited_urls = max(0, visited)
                stored.queued_urls = max(0, queued)
                stored.pages_kept = max(0, pages_kept)
                stored.index_done = max(0, int(progress.get("index_done", stored.index_done)))
                stored.index_total = max(0, int(progress.get("index_total", stored.index_total)))

                if phase == "crawl":
                    estimated = _estimate_crawl_progress(
                        stored.visited_urls,
                        stored.queued_urls,
                        stored.max_pages,
                    )
                    stored.progress_percent = max(stored.progress_percent, estimated)
                elif phase == "index":
                    index_total = stored.index_total
                    index_done = stored.index_done
                    if index_total > 0:
                        ratio = min(1.0, index_done / index_total)
                        # Keep a completion slot for final commit/cleanup before succeeded=100.
                        index_progress = 90 + int(ratio * 9)
                        stored.progress_percent = max(stored.progress_percent, min(99, index_progress))
                    else:
                        stored.progress_percent = max(stored.progress_percent, 90)

                self._persist_jobs_locked()

        try:
            site = SiteDefinition(
                site_id=job.site_id,
                site_name=job.site_name,
                start_url=job.start_url,
                allowed_host=job.allowed_host,
                allowed_path_prefix=job.allowed_path_prefix,
                start_urls=job.start_urls,
                allowed_path_prefixes=job.allowed_path_prefixes,
            )
            result = run_ingest_for_site(
                site,
                incremental=job.incremental,
                max_pages=job.max_pages,
                delay=job.delay,
                crawl_progress_every=0,
                collection_name=self.collection_name,
                embedding_model_name=self.embedding_model_name,
                reset_collection=False,
                progress_callback=_on_progress,
                auth_session=self._job_auth_session.get(job_id),
            )
            with self.jobs_lock:
                stored = self.jobs.get(job_id)
                if stored is None:
                    return
                stored.status = "succeeded"
                stored.phase = "completed"
                stored.progress_percent = 100
                stored.pages_kept = result.pages_scraped
                stored.visited_urls = max(stored.visited_urls, result.pages_scraped)
                stored.queued_urls = 0
                stored.index_done = max(stored.index_done, result.indexed_chunks)
                stored.index_total = max(stored.index_total, result.indexed_chunks)
                stored.finished_at = _now_iso()
                stored.result = _result_to_dict(result)
                stored.error = None
                stored.needs_authentication = False
                stored.detected_login_url = None
                self._persist_jobs_locked()

            self._job_auth_session.pop(job_id, None)

            with self.sync_lock:
                finished_at = stored.finished_at
                sync = self._get_or_create_sync_locked(site)
                sync.last_job_id = job_id
                sync.last_status = "succeeded"
                sync.last_scrape_finished_at = finished_at
                sync.last_successful_scrape_at = finished_at
                sync.last_indexed_at = finished_at
                sync.last_pages_scraped = result.pages_scraped
                sync.last_indexed_chunks = result.indexed_chunks
                sync.last_error = None
                sync.updated_at = _now_iso()
                self._persist_sync_locked()
        except AuthenticationRequiredError as exc:
            with self.jobs_lock:
                stored = self.jobs.get(job_id)
                if stored is None:
                    return
                stored.status = "awaiting_authentication"
                stored.phase = "awaiting_authentication"
                stored.needs_authentication = True
                stored.detected_login_url = exc.login_url or stored.start_url
                stored.error = str(exc)
                self._persist_jobs_locked()

            with self.sync_lock:
                site = SiteDefinition(
                    site_id=job.site_id,
                    site_name=job.site_name,
                    start_url=job.start_url,
                    allowed_host=job.allowed_host,
                    allowed_path_prefix=job.allowed_path_prefix,
                    start_urls=job.start_urls,
                    allowed_path_prefixes=job.allowed_path_prefixes,
                )
                sync = self._get_or_create_sync_locked(site)
                sync.last_job_id = job_id
                sync.last_status = "awaiting_authentication"
                sync.last_error = str(exc)
                sync.updated_at = _now_iso()
                self._persist_sync_locked()
        except Exception as exc:  # noqa: BLE001 - persist any ingest failure cause on the job record
            with self.jobs_lock:
                stored = self.jobs.get(job_id)
                if stored is None:
                    return
                stored.status = "failed"
                stored.phase = "failed"
                stored.progress_percent = min(stored.progress_percent, 99)
                stored.finished_at = _now_iso()
                stored.error = str(exc)
                stored.needs_authentication = False
                self._persist_jobs_locked()

            self._job_auth_session.pop(job_id, None)

            with self.sync_lock:
                site = SiteDefinition(
                    site_id=job.site_id,
                    site_name=job.site_name,
                    start_url=job.start_url,
                    allowed_host=job.allowed_host,
                    allowed_path_prefix=job.allowed_path_prefix,
                    start_urls=job.start_urls,
                    allowed_path_prefixes=job.allowed_path_prefixes,
                )
                sync = self._get_or_create_sync_locked(site)
                sync.last_job_id = job_id
                sync.last_status = "failed"
                sync.last_scrape_finished_at = stored.finished_at
                sync.last_error = str(exc)
                sync.updated_at = _now_iso()
                self._persist_sync_locked()

    def set_ingest_auth_session(
        self,
        *,
        job_id: str,
        cookies: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        with self.jobs_lock:
            job = self.jobs.get(job_id)
            if job is None:
                return {
                    "status": "not_found",
                    "job_id": job_id,
                    "message": "No ingest job found for this job_id.",
                }
            if job.status != "awaiting_authentication":
                return {
                    "status": "invalid_state",
                    "job_id": job_id,
                    "site_id": job.site_id,
                    "current_status": job.status,
                    "message": "Job is not waiting for authentication.",
                }

            clean_cookies = {str(k): str(v) for k, v in (cookies or {}).items() if str(k).strip()}
            clean_headers = {str(k): str(v) for k, v in (headers or {}).items() if str(k).strip()}
            if not clean_cookies and not clean_headers:
                return {
                    "status": "invalid_payload",
                    "job_id": job_id,
                    "site_id": job.site_id,
                    "message": "Provide at least one cookie or header to resume authentication.",
                }

            self._job_auth_session[job_id] = {"cookies": clean_cookies, "headers": clean_headers}
            job.status = "queued"
            job.phase = "queued"
            job.needs_authentication = False
            job.error = None
            self._persist_jobs_locked()

        thread = threading.Thread(target=self._run_ingest_job, args=(job_id,), daemon=True)
        thread.start()
        return {
            "status": "authentication_session_set",
            "job_id": job_id,
            "message": "Authentication session set. Ingestion resumed.",
        }

    def authenticate_ingest_job(self, *, job_id: str, timeout_seconds: float = 300.0) -> dict[str, Any]:
        if timeout_seconds <= 0 or timeout_seconds > 1800:
            raise ValueError("timeout_seconds must be between 0 and 1800")

        with self.jobs_lock:
            job = self.jobs.get(job_id)
            if job is None:
                return {
                    "status": "not_found",
                    "job_id": job_id,
                    "message": "No ingest job found for this job_id.",
                }
            if job.status != "awaiting_authentication":
                return {
                    "status": "invalid_state",
                    "job_id": job_id,
                    "site_id": job.site_id,
                    "current_status": job.status,
                    "message": "Job is not waiting for authentication.",
                }

            login_url = job.detected_login_url or job.start_url
            job.phase = "authenticating"
            self._persist_jobs_locked()

        try:
            auth_session = self._capture_authenticated_session_threadsafe(
                start_url=login_url,
                allowed_host=job.allowed_host,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - propagate capture failure reason to API payload
            with self.jobs_lock:
                stored = self.jobs.get(job_id)
                if stored is not None:
                    stored.status = "awaiting_authentication"
                    stored.phase = "awaiting_authentication"
                    stored.needs_authentication = True
                    stored.error = f"Authentication capture failed: {exc}"
                    self._persist_jobs_locked()
            return {
                "status": "authentication_failed",
                "job_id": job_id,
                "site_id": job.site_id,
                "message": f"Authentication capture failed: {exc}",
            }

        cookies = auth_session.get("cookies") or {}
        headers = auth_session.get("headers") or {}
        if not cookies and not headers:
            with self.jobs_lock:
                stored = self.jobs.get(job_id)
                if stored is not None:
                    stored.status = "awaiting_authentication"
                    stored.phase = "awaiting_authentication"
                    stored.needs_authentication = True
                    stored.error = "Authentication capture returned no cookies or session headers for target host."
                    self._persist_jobs_locked()
            return {
                "status": "authentication_failed",
                "job_id": job_id,
                "site_id": job.site_id,
                "message": "Authentication capture returned no cookies or session headers for target host.",
            }

        with self.jobs_lock:
            stored = self.jobs.get(job_id)
            if stored is None:
                return {
                    "status": "not_found",
                    "job_id": job_id,
                    "message": "No ingest job found for this job_id.",
                }
            self._job_auth_session[job_id] = auth_session
            stored.status = "queued"
            stored.phase = "queued"
            stored.needs_authentication = False
            stored.error = None
            self._persist_jobs_locked()

        with self.sync_lock:
            site = SiteDefinition(
                site_id=job.site_id,
                site_name=job.site_name,
                start_url=job.start_url,
                allowed_host=job.allowed_host,
                allowed_path_prefix=job.allowed_path_prefix,
            )
            sync = self._get_or_create_sync_locked(site)
            sync.last_job_id = job_id
            sync.last_status = "queued"
            sync.last_error = None
            sync.updated_at = _now_iso()
            self._persist_sync_locked()

        thread = threading.Thread(target=self._run_ingest_job, args=(job_id,), daemon=True)
        thread.start()

        return {
            "status": "authentication_captured",
            "job_id": job_id,
            "site_id": job.site_id,
            "message": "Authentication captured. Ingestion resumed.",
        }

    def set_ingest_auth_config(
        self,
        *,
        job_id: str,
        auth_config: dict[str, Any],
        timeout_seconds: float = 300.0,
    ) -> dict[str, Any]:
        if timeout_seconds <= 0 or timeout_seconds > 1800:
            raise ValueError("timeout_seconds must be between 0 and 1800")

        with self.jobs_lock:
            job = self.jobs.get(job_id)
            if job is None:
                return {
                    "status": "not_found",
                    "job_id": job_id,
                    "message": "No ingest job found for this job_id.",
                }
            if job.status != "awaiting_authentication":
                return {
                    "status": "invalid_state",
                    "job_id": job_id,
                    "site_id": job.site_id,
                    "current_status": job.status,
                    "message": "Job is not waiting for authentication.",
                }

            if not isinstance(auth_config, dict) or not auth_config:
                return {
                    "status": "invalid_payload",
                    "job_id": job_id,
                    "site_id": job.site_id,
                    "message": "auth_config must be a non-empty object.",
                }

            login_url = str(auth_config.get("login_url") or job.detected_login_url or job.start_url)
            job.phase = "authenticating"
            self._persist_jobs_locked()

        try:
            typed_auth_config = cast(AuthConfig, auth_config)
            auth_session = self._capture_authenticated_session_threadsafe(
                start_url=login_url,
                allowed_host=job.allowed_host,
                timeout_seconds=timeout_seconds,
                auth_config=typed_auth_config,
            )
        except Exception as exc:  # noqa: BLE001 - propagate auth-config capture failure to API payload
            with self.jobs_lock:
                stored = self.jobs.get(job_id)
                if stored is not None:
                    stored.status = "awaiting_authentication"
                    stored.phase = "awaiting_authentication"
                    stored.needs_authentication = True
                    stored.error = f"Authentication config failed: {exc}"
                    self._persist_jobs_locked()
            return {
                "status": "authentication_failed",
                "job_id": job_id,
                "site_id": job.site_id,
                "message": f"Authentication config failed: {exc}",
            }

        cookies = auth_session.get("cookies") or {}
        headers = auth_session.get("headers") or {}
        if not cookies and not headers:
            with self.jobs_lock:
                stored = self.jobs.get(job_id)
                if stored is not None:
                    stored.status = "awaiting_authentication"
                    stored.phase = "awaiting_authentication"
                    stored.needs_authentication = True
                    stored.error = "Authentication config produced no cookies or session headers."
                    self._persist_jobs_locked()
            return {
                "status": "authentication_failed",
                "job_id": job_id,
                "site_id": job.site_id,
                "message": "Authentication config produced no cookies or session headers.",
            }

        with self.jobs_lock:
            stored = self.jobs.get(job_id)
            if stored is None:
                return {
                    "status": "not_found",
                    "job_id": job_id,
                    "message": "No ingest job found for this job_id.",
                }
            self._job_auth_session[job_id] = auth_session
            stored.status = "queued"
            stored.phase = "queued"
            stored.needs_authentication = False
            stored.error = None
            self._persist_jobs_locked()

        with self.sync_lock:
            site = SiteDefinition(
                site_id=job.site_id,
                site_name=job.site_name,
                start_url=job.start_url,
                allowed_host=job.allowed_host,
                allowed_path_prefix=job.allowed_path_prefix,
            )
            sync = self._get_or_create_sync_locked(site)
            sync.last_job_id = job_id
            sync.last_status = "queued"
            sync.last_error = None
            sync.updated_at = _now_iso()
            self._persist_sync_locked()

        thread = threading.Thread(target=self._run_ingest_job, args=(job_id,), daemon=True)
        thread.start()

        return {
            "status": "authentication_config_applied",
            "job_id": job_id,
            "site_id": job.site_id,
            "message": "Authentication config applied. Ingestion resumed.",
        }

    @staticmethod
    def _capture_authenticated_session_threadsafe(
        *,
        start_url: str,
        allowed_host: str,
        timeout_seconds: float,
        auth_config: AuthConfig | None = None,
    ) -> AuthSession:
        result_holder: dict[str, AuthSession] = {}
        error_holder: dict[str, BaseException] = {}

        def _worker() -> None:
            try:
                result_holder["session"] = capture_authenticated_session(
                    start_url=start_url,
                    allowed_host=allowed_host,
                    auth_config=auth_config,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001  # pragma: no cover - passthrough from Playwright internals
                error_holder["error"] = exc

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        thread.join(timeout_seconds + 15)

        if thread.is_alive():
            raise TimeoutError(
                "Authentication capture timed out while waiting for browser login completion."
            )

        if "error" in error_holder:
            raise error_holder["error"]

        return result_holder.get("session", {"cookies": {}, "headers": {}})

    def get_job(self, job_id: str) -> IngestJobRecord | None:
        with self.jobs_lock:
            return self.jobs.get(job_id)

    async def wait_for_ingest_completion(
        self,
        *,
        job_id: str,
        poll_interval_seconds: float,
        timeout_seconds: float,
        ctx: Context | None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            job = self.get_job(job_id)

            if job is None:
                return {
                    "status": "not_found",
                    "job_id": job_id,
                    "message": "No ingest job found for this job_id.",
                }

            if job.status not in ACTIVE_JOB_STATUSES:
                if job.status == "awaiting_authentication":
                    payload = _job_to_dict(job)
                    payload["progress_bar"] = format_progress_bar(job.progress_percent)
                    payload["message"] = (
                        "Authentication is required. Call authenticate_ingest_job(job_id) "
                        "for interactive SSO or set_ingest_auth_session(job_id, cookies, headers) "
                        "to resume with an existing session, or set_ingest_auth_config(job_id, auth_config) "
                        "for form/cookie/basic/oauth strategies."
                    )
                    return payload
                await _ctx_info_safe(
                    ctx,
                    f"Ingestion update: {format_progress_bar(100)} status={job.status} phase={job.phase}",
                )
                await _ctx_progress_safe(
                    ctx,
                    100,
                    100,
                    message=f"{format_progress_bar(100)} ingestion finished with status '{job.status}'.",
                )
                payload = _job_to_dict(job)
                payload["progress_bar"] = format_progress_bar(job.progress_percent)
                payload["message"] = "Ingestion finished."
                return payload

            if time.monotonic() >= deadline:
                payload = _job_to_dict(job)
                payload["status"] = "timeout"
                payload["progress_bar"] = format_progress_bar(job.progress_percent)
                payload["message"] = "Job still running. Keep polling with ingest_status(job_id) or call wait_for_ingest_completion again."
                await _ctx_info_safe(
                    ctx,
                    f"Ingestion update: {_format_progress_message(job)} status=timeout",
                )
                return payload

            await _ctx_info_safe(ctx, f"Ingestion update: {_format_progress_message(job)}")
            await _ctx_progress_safe(
                ctx,
                float(job.progress_percent),
                100,
                message=_format_progress_message(job),
            )

            await asyncio.sleep(poll_interval_seconds)
