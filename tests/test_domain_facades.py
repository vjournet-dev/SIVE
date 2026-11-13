from sive.domain import (
    IngestRuntime,
    format_search_results,
    install_skill_files,
    rerank_search_results,
    run_ingest_for_site,
)
from sive.domain.client_install import service as skill_install_service
from sive.domain.ingest import service as ingest_service
from sive.domain.rerank import engine as rerank_engine
from sive.domain.runtime_state import runtime as mcp_runtime


def test_domain_ingestion_facade_exports_ingest_entrypoint():
    assert run_ingest_for_site is ingest_service.run_ingest_for_site


def test_domain_retrieval_facade_exports_search_helpers():
    assert format_search_results is rerank_engine.format_search_results
    assert rerank_search_results is rerank_engine.rerank_search_results


def test_domain_runtime_state_facade_exports_runtime_class():
    assert IngestRuntime is mcp_runtime.IngestRuntime


def test_domain_client_install_facade_exports_install_functions():
    assert install_skill_files is skill_install_service.install_skill_files
