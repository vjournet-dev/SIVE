from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer
else:
    MCPServer = Any


def _create_mcp_server(name: str) -> Any:
    try:
        from mcp.server.mcpserver import MCPServer as MCPServerClass
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "MCPServer is not available. Install/upgrade dependency 'mcp>=2.0.0' in the runtime environment."
        ) from exc
    return MCPServerClass(name)


def build_server(
    *,
    chroma_path: str,
    collection_name: str,
    embedding_model_name: str,
    chromadb_module: Any,
    apply_hf_token_from_env_func: Callable[[], str | None],
    get_collection_from_client_func: Callable[[Any, str, str], Any],
    ingest_runtime_cls: Any,
    register_admin_tools_func: Callable[..., None],
    register_search_tools_func: Callable[..., None],
    register_ingest_tools_func: Callable[..., None],
    validate_ingest_start_url_func: Callable[..., dict[str, Any] | None],
    resolve_ingest_input_func: Callable[..., dict[str, Any]],
    format_progress_bar_func: Callable[[int, int], str],
    catalog_repository_cls: Any,
    catalog_service_cls: Any,
    search_repository_cls: Any,
    search_service_cls: Any,
    format_ranked_search_results_func: Callable[[list[Any]], str],
    ddgs_factory: Any,
    httpx_client_factory: Any,
    find_best_topic_route_func: Callable[..., Any],
    refine_doc_start_url_func: Callable[..., str],
    search_doc_urls_on_web_func: Callable[..., list[dict[str, str]]],
    site_from_local_path_func: Callable[..., Any],
    site_from_url_func: Callable[..., Any],
    site_from_urls_func: Callable[..., Any],
    jobs_state_path: Any,
    routes_state_path: Any,
    sync_state_path: Any,
    site_index_state_path_func: Callable[[str], Any],
    site_raw_docs_path_func: Callable[[str], Any],
    format_json_func: Callable[[Any], str],
    job_to_dict_func: Callable[[Any], dict[str, Any]],
    normalize_topic_func: Callable[[str], str],
    rank_sync_records_func: Callable[..., list[Any]],
    sync_to_dict_func: Callable[[Any], dict[str, Any]],
    sync_staleness_seconds_func: Callable[..., int | None],
) -> MCPServer:
    server = _create_mcp_server("sive")
    client = chromadb_module.PersistentClient(path=chroma_path)
    apply_hf_token_from_env_func()
    collection = get_collection_from_client_func(client, collection_name, embedding_model_name)
    runtime = ingest_runtime_cls(
        collection=collection,
        jobs_state_path=jobs_state_path,
        routes_state_path=routes_state_path,
        sync_state_path=sync_state_path,
        collection_name=collection_name,
        embedding_model_name=embedding_model_name,
    )
    search_repository = search_repository_cls(collection)
    search_service = search_service_cls(search_repository, normalize_topic=normalize_topic_func)
    catalog_repository = catalog_repository_cls(collection)
    catalog_service = catalog_service_cls(
        catalog_repository,
        runtime=runtime,
        site_raw_docs_path=site_raw_docs_path_func,
        site_index_state_path=site_index_state_path_func,
    )

    def _refine_doc_start_url_with_http(url: str) -> str:
        return refine_doc_start_url_func(url, http_client_factory=httpx_client_factory)

    def _search_doc_urls_on_web_with_deps(topic: str, max_results: int) -> list[dict[str, str]]:
        return search_doc_urls_on_web_func(
            topic,
            max_results,
            ddgs_factory=ddgs_factory,
            refine_url=_refine_doc_start_url_with_http,
        )

    def _validate_ingest_start_url(url: str) -> dict[str, Any] | None:
        return validate_ingest_start_url_func(
            url,
            refine_doc_start_url=_refine_doc_start_url_with_http,
            http_client_factory=httpx_client_factory,
        )

    def _resolve_ingest_input(value: str, max_suggestions: int = 5) -> dict[str, Any]:
        return resolve_ingest_input_func(
            value,
            search_doc_urls_on_web=_search_doc_urls_on_web_with_deps,
            max_suggestions=max_suggestions,
        )

    register_admin_tools_func(
        server,
        catalog_service=catalog_service,
        runtime=runtime,
        format_json=format_json_func,
        rank_sync_records=rank_sync_records_func,
        sync_to_dict=sync_to_dict_func,
        sync_staleness_seconds=sync_staleness_seconds_func,
        format_progress_bar=format_progress_bar_func,
        job_to_dict=job_to_dict_func,
    )

    register_search_tools_func(
        server,
        search_service=search_service,
        runtime=runtime,
        find_best_topic_route=find_best_topic_route_func,
        format_json=format_json_func,
        search_doc_urls_on_web=_search_doc_urls_on_web_with_deps,
        format_search_results=format_ranked_search_results_func,
    )

    register_ingest_tools_func(
        server,
        runtime=runtime,
        format_json=format_json_func,
        normalize_topic=normalize_topic_func,
        site_from_url=site_from_url_func,
        site_from_local_path=site_from_local_path_func,
        validate_ingest_start_url=_validate_ingest_start_url,
        resolve_ingest_input=_resolve_ingest_input,
        site_from_urls=site_from_urls_func,
    )

    return server


def run_server(*, build_server_func: Callable[[], MCPServer]) -> None:
    server = build_server_func()
    server.run(transport="stdio")
