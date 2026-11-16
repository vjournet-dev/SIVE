"""MCP server app entrypoints."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import httpx
from ddgs import DDGS

if TYPE_CHECKING:
	from mcp.server.mcpserver import MCPServer
else:
	MCPServer = Any

from ...config import (
	CHROMA_DIR,
	DEFAULT_COLLECTION_NAME,
	INGEST_JOBS_STATE_PATH,
	SITE_SYNC_STATE_PATH,
	TOPIC_ROUTES_STATE_PATH,
	site_index_state_path,
	site_raw_docs_path,
)
from ...domain.catalog import DocumentationCatalogService
from ...domain.core.sites import site_from_local_path, site_from_url, site_from_urls
from ...domain.discovery import refine_doc_start_url, search_documentation_urls
from ...domain.ingest.input_resolution import resolve_ingest_input, validate_ingest_start_url
from ...domain.rerank.engine import format_ranked_search_results
from ...domain.routing import find_best_topic_route, normalize_topic
from ...domain.runtime_state.progress import format_progress_bar
from ...domain.runtime_state.runtime import IngestRuntime
from ...domain.runtime_state.state import (
	_format_json,
	_job_to_dict,
	_rank_sync_records,
	_sync_staleness_seconds,
	_sync_to_dict,
)
from ...domain.search import DocumentationSearchService
from ...infra.vector_store.catalog import ChromaDocumentationCatalogRepository
from ...infra.vector_store.chroma import get_collection_from_client as _infra_get_collection_from_client
from ...infra.vector_store.embedding_loader import (
	DEFAULT_EMBEDDING_MODEL_NAME,
	get_sentence_transformer_embedding_function,
)
from ...infra.vector_store.hf_auth import apply_hf_token_from_env
from ...infra.vector_store.lazy import LazyCollection
from ...infra.vector_store.search import ChromaDocumentationSearchRepository
from . import server as _app_server
from .tools_admin import register_admin_tools
from .tools_ingest import register_ingest_tools
from .tools_search import register_search_tools

__all__ = ["build_server", "run_server"]

# Lazily loaded to keep non-server CLI paths from importing chromadb on startup.
chromadb: Any = SimpleNamespace(PersistentClient=None)


def _resolve_chromadb_module() -> Any:
	global chromadb
	if getattr(chromadb, "PersistentClient", None) is None:
		chromadb = importlib.import_module("chromadb")
	return chromadb


def get_collection_from_client(client: object, collection_name: str, embedding_model_name: str, *, reset_collection: bool = False) -> object:
	return _infra_get_collection_from_client(
		client,
		collection_name,
		embedding_model_name,
		get_sentence_transformer_embedding_function_func=get_sentence_transformer_embedding_function,
		reset_collection=reset_collection,
	)


def _open_collection(chroma_path: str, collection_name: str, embedding_model_name: str) -> object:
	chromadb_module = _resolve_chromadb_module()
	client = chromadb_module.PersistentClient(path=chroma_path)
	apply_hf_token_from_env()
	return get_collection_from_client(client, collection_name, embedding_model_name)


def build_server(
	chroma_path: str = str(CHROMA_DIR),
	collection_name: str = DEFAULT_COLLECTION_NAME,
	embedding_model_name: str = DEFAULT_EMBEDDING_MODEL_NAME,
	*,
	warm_up: bool = False,
) -> MCPServer:
	# Opening the collection imports chromadb/torch and loads the embedding model (tens of seconds), which
	# exceeds MCP client startup timeouts. It is therefore deferred to first use, or to a background warm-up.
	collection = LazyCollection(lambda: _open_collection(chroma_path, collection_name, embedding_model_name))
	server = _app_server.build_server(
		collection=collection,
		collection_name=collection_name,
		embedding_model_name=embedding_model_name,
		ingest_runtime_cls=IngestRuntime,
		register_admin_tools_func=register_admin_tools,
		register_search_tools_func=register_search_tools,
		register_ingest_tools_func=register_ingest_tools,
		validate_ingest_start_url_func=validate_ingest_start_url,
		resolve_ingest_input_func=resolve_ingest_input,
		format_progress_bar_func=format_progress_bar,
		catalog_repository_cls=ChromaDocumentationCatalogRepository,
		catalog_service_cls=DocumentationCatalogService,
		search_repository_cls=ChromaDocumentationSearchRepository,
		search_service_cls=DocumentationSearchService,
		format_ranked_search_results_func=format_ranked_search_results,
		ddgs_factory=DDGS,
		httpx_client_factory=httpx.Client,
		find_best_topic_route_func=find_best_topic_route,
		refine_doc_start_url_func=refine_doc_start_url,
		search_doc_urls_on_web_func=search_documentation_urls,
		site_from_local_path_func=site_from_local_path,
		site_from_url_func=site_from_url,
		site_from_urls_func=site_from_urls,
		jobs_state_path=INGEST_JOBS_STATE_PATH,
		routes_state_path=TOPIC_ROUTES_STATE_PATH,
		sync_state_path=SITE_SYNC_STATE_PATH,
		site_index_state_path_func=site_index_state_path,
		site_raw_docs_path_func=site_raw_docs_path,
		format_json_func=_format_json,
		job_to_dict_func=_job_to_dict,
		normalize_topic_func=normalize_topic,
		rank_sync_records_func=_rank_sync_records,
		sync_to_dict_func=_sync_to_dict,
		sync_staleness_seconds_func=_sync_staleness_seconds,
	)
	if warm_up:
		collection.warm_up()
	return server


def run_server() -> None:
	_app_server.run_server(build_server_func=lambda: build_server(warm_up=True))
