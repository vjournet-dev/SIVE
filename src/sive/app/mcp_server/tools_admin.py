from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from mcp.server.mcpserver import Context, MCPServer

from ...domain.catalog import DocumentationCatalogService
from ...domain.runtime_state.runtime import IngestRuntime
from .annotations import DESTRUCTIVE, READ_ONLY


async def _emit_progress_safe(ctx: Context | None, info_message: str, progress_percent: float, bar_message: str) -> None:
    """Emit MCP progress only when request context is actually available."""
    if ctx is None:
        return
    try:
        await ctx.info(info_message)
        await ctx.report_progress(progress_percent, 100, message=bar_message)
    except ValueError:
        # MCPServer may provide a Context object outside an active request session.
        return


def register_admin_tools(
    server: MCPServer,
    *,
    catalog_service: DocumentationCatalogService,
    runtime: IngestRuntime,
    format_json: Callable[[Any], str],
    rank_sync_records: Callable[..., list[Any]],
    sync_to_dict: Callable[[Any], dict[str, Any]],
    sync_staleness_seconds: Callable[[Any, datetime | None], int | None],
    format_progress_bar: Callable[[int, int], str],
    job_to_dict: Callable[[Any], dict[str, Any]],
) -> None:
    @server.tool(annotations=READ_ONLY)
    def list_indexed_doc_sites() -> str:
        """Compact list of the documentation sites that are ready to search (site_id and name).

        Sites currently being ingested are hidden until their job completes, to avoid using partially
        updated docs; follow such a job with wait_for_ingest_completion(job_id).
        Prefer list_documentation_sites_in_database for discovery: it also reports document counts and
        which sites are ingesting.
        """
        active_sites = runtime.active_site_ids()
        visible, hidden_visible = catalog_service.indexed_sites(active_site_ids=active_sites)

        if not visible:
            if active_sites:
                hidden = ", ".join(sorted(active_sites))
                return (
                    "No indexed documentation sites are currently available. "
                    f"Sites currently ingesting and hidden from listing: {hidden}."
                )
            return "No indexed documentation sites found."

        lines = [f"- {site_name} ({site_id})" for site_id, site_name in visible]
        if hidden_visible:
            lines.append("")
            lines.append("Temporarily hidden while ingesting: " + ", ".join(hidden_visible))
        return "\n".join(lines)

    @server.tool(annotations=READ_ONLY)
    def list_documentation_sites_in_database(include_active: bool = True) -> str:
        """Discovery step before searching: list the indexed documentation sites.

        Returns JSON with each site's site_id, name, document count and active-ingestion flag. Match the
        library, product and version of the task to a site_id, then call search_documentation with it.
        Reuse the result for the rest of the conversation; call it again after an ingestion or a removal.
        Use include_active=False to hide the sites currently being ingested.
        The first call after the server starts can be slow while the index opens; wait for it.
        """
        payload = catalog_service.list_sites(
            active_site_ids=runtime.active_site_ids(),
            include_active=include_active,
        )
        return format_json(payload)

    @server.tool(annotations=READ_ONLY)
    def get_site_sync_status(site_id: str) -> str:
        """Return persisted scraping/indexing timestamps for a documentation site."""
        cleaned_site_id = site_id.strip()
        if not cleaned_site_id:
            raise ValueError("site_id must be a non-empty string")

        sync = runtime.get_sync(cleaned_site_id)

        if sync is None:
            return format_json(
                {
                    "status": "not_found",
                    "site_id": cleaned_site_id,
                    "message": "No sync history found for this site_id. Run ingest(url) first.",
                }
            )

        payload = sync_to_dict(sync)
        payload["status"] = "ok"
        payload["message"] = "Timestamps are stored in UTC ISO-8601 format."
        return format_json(payload)

    @server.tool(annotations=READ_ONLY)
    def list_site_sync_status(
        sort_by: str = "staleness",
        descending: bool = True,
        limit: int = 100,
    ) -> str:
        """List sync status for all known sites, sorted for update prioritization."""
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")

        records = runtime.list_sync_records()

        ranked = rank_sync_records(records, sort_by=sort_by, descending=descending)
        ranked = ranked[:limit]

        active_site_ids = runtime.active_job_site_ids()

        now_dt = datetime.now(UTC)
        items: list[dict[str, Any]] = []
        for sync in ranked:
            payload = sync_to_dict(sync)
            staleness = sync_staleness_seconds(sync, now_dt)
            payload["staleness_seconds"] = staleness
            payload["has_active_job"] = sync.site_id in active_site_ids
            payload["recommended_action"] = (
                "wait_for_ingest_completion"
                if sync.site_id in active_site_ids
                else "update_site_differential"
            )
            items.append(payload)

        return format_json(
            {
                "status": "ok",
                "sort_by": sort_by,
                "descending": descending,
                "total": len(records),
                "returned": len(items),
                "items": items,
                "message": "Use update_site_differential(site_id) on stale sites without active jobs.",
            }
        )

    @server.tool(annotations=DESTRUCTIVE)
    def delete_documentation_site(site_id: str, delete_raw_files: bool = True) -> str:
        """Permanently delete a documentation site from Chroma and local persisted state.

        By default, this also deletes raw crawl/state files for the site.
        Destructive: call it only when the user explicitly asked to remove that site.
        """
        payload = catalog_service.delete_site(
            site_id,
            delete_raw_files=delete_raw_files,
        )
        return format_json(payload)

    @server.tool(annotations=READ_ONLY)
    async def ingest_status(job_id: str, ctx: Context | None = None) -> str:
        """Get status and result details for a previously started ingest job (single poll)."""
        job = runtime.get_job(job_id)

        if job is None:
            return format_json(
                {
                    "status": "not_found",
                    "job_id": job_id,
                    "message": "No ingest job found for this job_id.",
                }
            )

        payload = job_to_dict(job)
        payload["progress_bar"] = format_progress_bar(int(job.progress_percent), 20)
        if job.phase == "index" and job.index_total > 0:
            payload["index_progress"] = f"{job.index_done}/{job.index_total}"
        if getattr(job, "needs_authentication", False):
            payload["message"] = (
                "Authentication is required. Call authenticate_ingest_job(job_id) "
                "for interactive SSO or set_ingest_auth_session(job_id, cookies, headers) "
                "to resume with an existing session, or set_ingest_auth_config(job_id, auth_config) "
                "for form/cookie/basic/oauth strategies."
            )
        else:
            payload["message"] = (
                "Use status/progress_percent/progress_bar to track progress: "
                "queued, running, awaiting_authentication, succeeded, failed."
            )
            if "index_progress" in payload:
                payload["message"] += " Indexing progress: index_progress (index_done/index_total)."
        index_hint = ""
        if job.phase == "index" and job.index_total > 0:
            index_hint = f" index={job.index_done}/{job.index_total}"
        await _emit_progress_safe(
            ctx,
            "Ingestion update: "
            f"{payload['progress_bar']} phase={job.phase} visited={job.visited_urls} "
            f"kept={job.pages_kept} queued={job.queued_urls}{index_hint} status={job.status}",
            float(job.progress_percent),
            payload["progress_bar"],
        )
        return format_json(payload)

    @server.tool(annotations=READ_ONLY)
    async def wait_for_ingest_completion(
        job_id: str,
        poll_interval_seconds: float = 2.0,
        timeout_seconds: float = 600.0,
        ctx: Context | None = None,
    ) -> str:
        """Wait until an ingest job completes or timeout_seconds elapses; the default way to follow a job.

        Reports progress while waiting. A timeout is not a failure: the job keeps running, so call this
        again or check ingest_status(job_id).
        """
        if poll_interval_seconds <= 0 or poll_interval_seconds > 30:
            raise ValueError("poll_interval_seconds must be between 0 and 30")
        if timeout_seconds <= 0 or timeout_seconds > 86400:
            raise ValueError("timeout_seconds must be between 0 and 86400")
        payload = await runtime.wait_for_ingest_completion(
            job_id=job_id,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
            ctx=ctx,
        )
        return format_json(payload)
