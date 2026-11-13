from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer
else:
    MCPServer = Any

from ...domain.rerank.engine import RankedSearchResult
from ...domain.runtime_state.runtime import IngestRuntime
from ...domain.runtime_state.state import TopicRouteRecord
from ...domain.search import DocumentationSearchService


def register_search_tools(
    server: MCPServer,
    *,
    search_service: DocumentationSearchService,
    runtime: IngestRuntime,
    find_best_topic_route: Callable[..., TopicRouteRecord | None],
    format_json: Callable[[Any], str],
    search_doc_urls_on_web: Callable[[str, int], list[dict[str, str]]],
    format_search_results: Callable[[list[RankedSearchResult]], str],
) -> None:
    @server.tool()
    def search_documentation(
        query: str,
        top_k: int = 5,
        site_id: str | None = None,
        site_ids: list[str] | None = None,
        topic: str | None = None,
    ) -> str:
        """Primary retrieval tool for accurate, project-level documentation.

        Always use this tool for detailed project questions and when training data may be outdated.
        Do not rely on memory alone when MCP retrieval is available.

        Mandatory workflow:
        1. Call list_indexed_doc_sites first.
        2. Use site_id filtering whenever the target product is known.
        3. Cite returned source URLs in the final answer.

        During ingestion:
        - search_documentation stays available.
        - If a specific site_id is currently ingesting, this tool returns a wait message for that site.

        Topic-aware behavior:
        - When site_id is omitted, a registered topic route can auto-select site_id from topic or query.
        - Register topic routes with ingest_and_register_topic.
        """
        if site_id and site_ids:
            raise ValueError("site_id and site_ids cannot be used together")

        selected_site_ids = tuple(
            dict.fromkeys(
                candidate.strip()
                for candidate in ([site_id] if site_id else (site_ids or []))
                if candidate and candidate.strip()
            )
        )
        route_used: TopicRouteRecord | None = None

        if not selected_site_ids:
            route_used = runtime.find_best_topic_route(query=query, topic=topic, finder=find_best_topic_route)
            if route_used is not None:
                selected_site_ids = route_used.site_ids
            else:
                selected_site_ids = search_service.match_site_ids(query)

        response = search_service.search(
            query,
            top_k=top_k,
            site_ids=selected_site_ids or None,
            active_site_ids=runtime.active_site_ids(),
        )
        if not response.results:
            if response.skipped_active_site_ids and not response.searched_site_ids:
                active_job_ids = [
                    job.job_id
                    for active_site_id in response.skipped_active_site_ids
                    for job in runtime.active_jobs_for_site(active_site_id)
                ]
                return (
                    f"All selected sites are currently being ingested: "
                    f"{', '.join(response.skipped_active_site_ids)}. "
                    f"Wait for completion with ingest_status(job_id). Active job_id(s): {', '.join(active_job_ids)}."
                )
            scope = f" for sites {', '.join(selected_site_ids)}" if selected_site_ids else ""
            return f"No result found in indexed docs{scope}."

        headers: list[str] = []
        if route_used is not None and not site_id and not site_ids:
            headers.append(
                f"Topic route applied: '{route_used.topic}' -> site_ids "
                f"'{', '.join(route_used.site_ids)}'."
            )
        if response.searched_site_ids:
            headers.append(f"Sites searched: {', '.join(response.searched_site_ids)}.")
        if response.skipped_active_site_ids:
            headers.append(f"Sites skipped while ingesting: {', '.join(response.skipped_active_site_ids)}.")

        search_result = format_search_results(list(response.results))
        return f"{' '.join(headers)}\n\n{search_result}" if headers else search_result

    @server.tool()
    def suggest_documentation_urls(topic: str, max_results: int = 5) -> str:
        """Find candidate documentation URLs on the web for a topic.

        Use when the user did not provide a documentation URL.
        Present suggestions to the user, ask for confirmation, then ingest the selected URL.
        """
        cleaned_topic = topic.strip()
        if not cleaned_topic:
            raise ValueError("topic must be a non-empty string")
        if max_results < 1 or max_results > 10:
            raise ValueError("max_results must be between 1 and 10")

        suggestions = search_doc_urls_on_web(cleaned_topic, max_results)
        if not suggestions:
            return format_json(
                {
                    "status": "no_suggestion",
                    "topic": cleaned_topic,
                    "message": "No documentation URL suggestion found from web search. Ask the user to provide an official URL.",
                }
            )

        return format_json(
            {
                "status": "ok",
                "topic": cleaned_topic,
                "suggestions": suggestions,
                "message": "Ask the user to pick one URL, then call ingest(url) or ingest_and_register_topic(topic, url).",
            }
        )
