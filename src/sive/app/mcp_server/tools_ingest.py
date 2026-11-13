from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer
else:
    MCPServer = Any

from ...domain.core.sites import SiteDefinition
from ...domain.ingest.input_resolution import looks_like_local_path
from ...domain.ingest.service import update_existing_local_site
from ...domain.runtime_state.progress import format_progress_bar
from ...domain.runtime_state.runtime import IngestRuntime


def register_ingest_tools(
    server: MCPServer,
    *,
    runtime: IngestRuntime,
    format_json: Callable[[Any], str],
    normalize_topic: Callable[[str], str],
    site_from_url: Callable[[str], SiteDefinition],
    site_from_local_path: Callable[[str], SiteDefinition],
    validate_ingest_start_url: Callable[[str], dict[str, Any] | None],
    resolve_ingest_input: Callable[[str, int], dict[str, Any]],
    site_from_urls: Callable[..., SiteDefinition] | None = None,
) -> None:
    @server.tool()
    def ingest(
        url: str,
        incremental: bool = True,
        max_pages: int = 1200,
        delay: float = 0.2,
        additional_urls: list[str] | None = None,
        allowed_url_prefixes: list[str] | None = None,
        site_id: str | None = None,
        site_name: str | None = None,
    ) -> str:
        """Start asynchronous ingestion for a documentation URL or a topic text query.

        The server derives the default crawl scope from the URL:
        - allowed_host = URL host
        - allowed_path_prefix = first path segment (or '/').

        To combine same-host documentation branches into one source, pass additional_urls.
        Their full paths become strict crawl prefixes by default, or provide
        allowed_url_prefixes as absolute URLs or path prefixes. Optional site_id and
        site_name identify the combined documentation source.

        Returns immediately with a job_id. Use ingest_status(job_id) for progress and final outcome.
        """
        if max_pages < 1 or max_pages > 20000:
            raise ValueError("max_pages must be between 1 and 20000")
        if delay < 0 or delay > 5:
            raise ValueError("delay must be between 0 and 5 seconds")

        resolution = resolve_ingest_input(url, 5)
        if resolution["status"] not in {"resolved_url", "resolved_local_path"}:
            return format_json(resolution)

        uses_custom_web_scope = bool(additional_urls or allowed_url_prefixes or site_id or site_name)
        if resolution["status"] == "resolved_local_path" and uses_custom_web_scope:
            return format_json(
                {
                    "status": "invalid_multi_url_scope",
                    "message": "additional_urls and allowed_url_prefixes are supported only for HTTP(S) documentation.",
                }
            )

        if resolution["status"] == "resolved_local_path":
            resolved_local_path = str(resolution["path"])
            site = site_from_local_path(resolved_local_path)
        else:
            resolved_url = str(resolution["url"])
            if uses_custom_web_scope:
                if site_from_urls is None:
                    raise RuntimeError("multi-URL ingest is not configured")
                try:
                    site = site_from_urls(
                        [resolved_url, *(additional_urls or [])],
                        allowed_url_prefixes=allowed_url_prefixes,
                        site_id=site_id,
                        site_name=site_name,
                    )
                except ValueError as exc:
                    return format_json({"status": "invalid_multi_url_scope", "message": str(exc)})
            else:
                site = site_from_url(resolved_url)

            for candidate_url in site.crawl_start_urls:
                validation_error = validate_ingest_start_url(candidate_url)
                if validation_error is not None:
                    validation_error["rejected_start_url"] = candidate_url
                    return format_json(validation_error)

        payload = runtime.enqueue_ingest_job(
            site,
            incremental=incremental,
            max_pages=max_pages,
            delay=delay,
        )
        if resolution.get("input_kind") == "query":
            payload["query"] = resolution.get("query")
            payload["resolved_url"] = resolved_url
            payload["selected_suggestion"] = resolution.get("selected_suggestion")
        elif resolution.get("input_kind") == "local_path":
            payload["resolved_local_path"] = resolution.get("path")

        return format_json(payload)

    @server.tool()
    def ingest_and_register_topic(
        topic: str,
        url: str,
        incremental: bool = True,
        max_pages: int = 1200,
        delay: float = 0.2,
        additional_urls: list[str] | None = None,
        allowed_url_prefixes: list[str] | None = None,
        site_id: str | None = None,
        site_name: str | None = None,
    ) -> str:
        """Register a documentation topic and start asynchronous ingestion from URL.

        If URL validation fails (for example HTTP 404), no topic route is persisted.
        """
        cleaned_topic = topic.strip()
        if not cleaned_topic:
            raise ValueError("topic must be a non-empty string")

        topic_key = normalize_topic(cleaned_topic)

        ingest_payload_raw = ingest(
            url=url,
            incremental=incremental,
            max_pages=max_pages,
            delay=delay,
            additional_urls=additional_urls,
            allowed_url_prefixes=allowed_url_prefixes,
            site_id=site_id,
            site_name=site_name,
        )
        try:
            ingest_payload = json.loads(ingest_payload_raw)
        except json.JSONDecodeError:
            ingest_payload = {"status": "error", "message": ingest_payload_raw}

        if ingest_payload.get("status") not in {"queued", "already_running"}:
            ingest_payload["topic"] = cleaned_topic
            ingest_payload["topic_key"] = topic_key
            ingest_payload["route_registered"] = False
            return format_json(ingest_payload)

        if additional_urls or allowed_url_prefixes or site_id or site_name:
            if site_from_urls is None:
                raise RuntimeError("multi-URL ingest is not configured")
            queued_start_urls = ingest_payload.get("start_urls")
            resolved_start_urls = (
                [str(item) for item in queued_start_urls]
                if isinstance(queued_start_urls, list)
                else [url, *(additional_urls or [])]
            )
            queued_prefixes = ingest_payload.get("allowed_path_prefixes")
            resolved_prefixes = (
                [str(item) for item in queued_prefixes]
                if isinstance(queued_prefixes, list)
                else allowed_url_prefixes
            )
            site = site_from_urls(
                resolved_start_urls,
                allowed_url_prefixes=resolved_prefixes,
                site_id=str(ingest_payload.get("site_id") or site_id or ""),
                site_name=str(ingest_payload.get("site_name") or site_name or ""),
            )
        else:
            site = site_from_url(url)
        runtime.update_topic_route(topic=cleaned_topic, topic_key=topic_key, site=site)

        ingest_payload["topic"] = cleaned_topic
        ingest_payload["topic_key"] = topic_key
        ingest_payload["route_registered"] = True
        return format_json(ingest_payload)

    @server.tool()
    def update_site_differential(site_id: str, max_pages: int = 1200, delay: float = 0.2) -> str:
        """Start a differential update for an already indexed documentation site.

        This tool resolves the site's crawl scope from server state, then starts
        an asynchronous ingestion with incremental mode forced to True.
        """
        cleaned_site_id = site_id.strip()
        if not cleaned_site_id:
            raise ValueError("site_id must be a non-empty string")
        if max_pages < 1 or max_pages > 20000:
            raise ValueError("max_pages must be between 1 and 20000")
        if delay < 0 or delay > 5:
            raise ValueError("delay must be between 0 and 5 seconds")

        site = runtime.resolve_existing_site(cleaned_site_id)
        if site is None:
            return format_json(
                {
                    "status": "site_not_found",
                    "site_id": cleaned_site_id,
                    "message": (
                        "No known crawl configuration found for this site_id. "
                        "Use ingest(url) first to register and index this documentation source."
                    ),
                }
            )

        validation_error = validate_ingest_start_url(site.start_url)
        if validation_error is not None:
            validation_error["site_id"] = cleaned_site_id
            return format_json(validation_error)

        payload = runtime.enqueue_ingest_job(site, incremental=True, max_pages=max_pages, delay=delay)
        payload["incremental"] = True
        payload["mode"] = "differential_update"
        return format_json(payload)

    @server.tool()
    def update_documentation_source(target: str, max_pages: int = 1200, delay: float = 0.2) -> str:
        """Update an existing documentation source by site_id (remote) or local path.

        - If target resolves to an existing local file/folder path, only already-indexed local
          documents that match this path are updated.
        - Otherwise target is interpreted as a site_id and runs differential web update.
        """
        cleaned_target = target.strip()
        if not cleaned_target:
            raise ValueError("target must be a non-empty string")

        resolved_target = Path(cleaned_target).expanduser()
        try:
            existing_local_path = resolved_target.resolve() if resolved_target.exists() else None
        except OSError:
            existing_local_path = None

        if existing_local_path is not None:
            payload = update_existing_local_site(
                str(existing_local_path),
                collection=runtime.collection,
            )
            payload["target_kind"] = "local_path"
            payload.setdefault("progress_percent", 100)
            payload.setdefault("progress_bar", format_progress_bar(int(payload["progress_percent"])))
            return format_json(payload)

        if looks_like_local_path(cleaned_target):
            return format_json(
                {
                    "status": "no_match",
                    "mode": "local_selective_update",
                    "target_kind": "local_path",
                    "target_path": cleaned_target,
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
            )

        payload_raw = update_site_differential(site_id=cleaned_target, max_pages=max_pages, delay=delay)
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = {"status": "error", "message": payload_raw}

        payload["target_kind"] = "site_id"
        payload["target"] = cleaned_target
        payload.setdefault("progress_percent", 0)
        payload.setdefault("progress_bar", format_progress_bar(int(payload["progress_percent"])))
        return format_json(payload)

    @server.tool()
    def authenticate_ingest_job(job_id: str, timeout_seconds: float = 300.0) -> str:
        """Open an interactive browser login flow and resume an auth-blocked ingestion job.

        Use this when ingest_status(job_id) returns status='awaiting_authentication'.
        """
        payload = runtime.authenticate_ingest_job(job_id=job_id, timeout_seconds=timeout_seconds)
        return format_json(payload)

    @server.tool()
    def set_ingest_auth_session(
        job_id: str,
        cookies: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        """Attach cookies/session headers to an auth-blocked job and resume ingestion.

        Use this for generic cookie/session workflows when users already have
        authentication material and do not need interactive browser login.
        """
        payload = runtime.set_ingest_auth_session(
            job_id=job_id,
            cookies=cookies,
            headers=headers,
        )
        return format_json(payload)

    @server.tool()
    def set_ingest_auth_config(
        job_id: str,
        auth_config: dict[str, Any],
        timeout_seconds: float = 300.0,
    ) -> str:
        """Attach an authentication config and resume an auth-blocked job.

        auth_config supports generic strategies inspired by handle_authentication:
        - form: {type, login_url?, username, password, selectors?}
        - cookie: {type, cookies}
        - basic: {type, username, password}
        - oauth: {type, token, token_type?, headers?}
        """
        payload = runtime.set_ingest_auth_config(
            job_id=job_id,
            auth_config=auth_config,
            timeout_seconds=timeout_seconds,
        )
        return format_json(payload)
