from sive.domain.catalog import DocumentationCatalogService
from sive.domain.ingest import input_resolution
from sive.domain.rerank import engine as rerank_engine
from sive.domain.runtime_state import state as mcp_state
from sive.infra.vector_store.catalog import ChromaDocumentationCatalogRepository


class _FakeValidateResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeValidateClient:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return _FakeValidateResponse(self.status_code)


def test_validate_ingest_start_url_returns_explicit_payload_on_404():
    result = input_resolution.validate_ingest_start_url(
        "https://playwright.dev/docs",
        refine_doc_start_url=lambda _url: "https://playwright.dev/docs/intro",
        http_client_factory=lambda **_: _FakeValidateClient(status_code=404),
    )

    assert result is not None
    assert result["status"] == "invalid_start_url"
    assert result["error_code"] == "url_not_found_404"
    assert result["http_status"] == 404
    assert result["url"] == "https://playwright.dev/docs"
    assert "first page of the documentation" in result["message"]
    assert "not the documentation root/home URL" in result["message"]
    assert result["suggested_start_url"] == "https://playwright.dev/docs/intro"


def test_validate_ingest_start_url_returns_none_when_url_is_ok():
    result = input_resolution.validate_ingest_start_url(
        "https://playwright.dev/docs/intro",
        refine_doc_start_url=lambda value: value,
        http_client_factory=lambda **_: _FakeValidateClient(status_code=200),
    )

    assert result is None


def test_resolve_ingest_input_returns_url_when_http_url_is_provided():
    result = input_resolution.resolve_ingest_input(
        "https://playwright.dev/docs/intro",
        search_doc_urls_on_web=lambda *_args: [],
    )

    assert result == {
        "status": "resolved_url",
        "input_kind": "url",
        "url": "https://playwright.dev/docs/intro",
    }


def test_resolve_ingest_input_returns_selected_url_for_single_suggestion():
    result = input_resolution.resolve_ingest_input(
        "playwright",
        search_doc_urls_on_web=lambda topic, max_results: [{"title": "Playwright docs", "url": "https://playwright.dev/docs/intro"}],
    )

    assert result["status"] == "resolved_url"
    assert result["input_kind"] == "query"
    assert result["query"] == "playwright"
    assert result["url"] == "https://playwright.dev/docs/intro"


def test_resolve_ingest_input_returns_needs_confirmation_for_multiple_suggestions():
    result = input_resolution.resolve_ingest_input(
        "playwright",
        search_doc_urls_on_web=lambda topic, max_results: [
            {"title": "Playwright docs", "url": "https://playwright.dev/docs/intro"},
            {"title": "Playwright API", "url": "https://playwright.dev/docs/api/class-playwright"},
        ],
    )

    assert result["status"] == "needs_confirmation"
    assert result["query"] == "playwright"
    assert len(result["suggestions"]) == 2


def test_resolve_ingest_input_returns_no_suggestion_when_search_empty():
    result = input_resolution.resolve_ingest_input(
        "unknown-doc",
        search_doc_urls_on_web=lambda topic, max_results: [],
    )

    assert result["status"] == "no_suggestion"
    assert result["query"] == "unknown-doc"


def test_resolve_ingest_input_returns_local_path_when_file_exists(tmp_path):
    file_path = tmp_path / "manual.html"
    file_path.write_text("<html><body>manual</body></html>", encoding="utf-8")

    result = input_resolution.resolve_ingest_input(
        str(file_path),
        search_doc_urls_on_web=lambda *_args: [],
    )

    assert result == {
        "status": "resolved_local_path",
        "input_kind": "local_path",
        "path": str(file_path.resolve()),
        "path_kind": "absolute",
    }


def test_resolve_ingest_input_returns_invalid_local_path_for_missing_relative_path():
    captured: dict[str, object] = {}

    def _search(query: str, max_results: int):
        captured["query"] = query
        captured["max_results"] = max_results
        return []

    result = input_resolution.resolve_ingest_input(
        "./docs/missing-manual",
        search_doc_urls_on_web=_search,
    )

    assert result["status"] == "invalid_local_path"
    assert result["input_kind"] == "local_path"
    assert result["path"] == "./docs/missing-manual"
    assert result["path_kind"] == "relative"
    assert "does not exist" in result["message"]
    assert captured == {}


def test_resolve_ingest_input_returns_invalid_local_path_for_missing_absolute_path(tmp_path):
    captured: dict[str, object] = {}

    def _search(query: str, max_results: int):
        captured["query"] = query
        captured["max_results"] = max_results
        return []

    missing_path = str((tmp_path / "missing" / "manual.csv").resolve())

    result = input_resolution.resolve_ingest_input(
        missing_path,
        search_doc_urls_on_web=_search,
    )

    assert result["status"] == "invalid_local_path"
    assert result["input_kind"] == "local_path"
    assert result["path"] == missing_path
    assert result["path_kind"] == "absolute"
    assert "does not exist" in result["message"]
    assert captured == {}


def test_format_search_results_shows_page_number_and_truncation_marker():
    long_doc = "A" * 1300

    result = rerank_engine.format_search_results(
        docs=[long_doc],
        metas=[
            {
                "source_url": "file:///manual.pdf",
                "title": "manual.pdf",
                "site_id": "pdf-doc",
                "site_name": "PDF Doc",
                "section_heading": "Page 2",
                "page_number": 2,
            }
        ],
        distances=[0.25],
    )

    assert "Section: Page 2 (page 2)" in result
    assert "[...truncated...]" in result


def test_format_search_results_shows_source_kind_and_section_type():
    result = rerank_engine.format_search_results(
        docs=["columns: name, role"],
        metas=[
            {
                "source_url": "file:///users.csv",
                "title": "users.csv",
                "site_id": "csv-doc",
                "site_name": "CSV Doc",
                "section_heading": "users.csv / Summary",
                "source_kind": "csv",
            }
        ],
        distances=[0.2],
    )

    assert "Source Kind: csv" in result
    assert "Section Type: summary" in result


def test_rerank_search_results_boosts_matching_section_heading():
    docs, metas, _distances = rerank_engine.rerank_search_results(
        query="configuration",
        docs=["generic body", "config body"],
        metas=[{"title": "Guide", "section_heading": "Overview"}, {"title": "Guide", "section_heading": "Configuration"}],
        distances=[0.1, 0.2],
        normalize_topic=mcp_state._normalize_topic,
    )

    assert metas[0]["section_heading"] == "Configuration"
    assert docs[0] == "config body"


def test_rerank_search_results_boosts_json_for_field_or_schema_queries():
    docs, metas, _distances = rerank_engine.rerank_search_results(
        query="json schema fields",
        docs=["html body", "json body"],
        metas=[
            {"title": "Guide", "section_heading": "Reference", "source_kind": "html"},
            {"title": "config.json", "section_heading": "schema", "source_kind": "json"},
        ],
        distances=[0.1, 0.18],
        normalize_topic=mcp_state._normalize_topic,
    )

    assert metas[0]["source_kind"] == "json"
    assert docs[0] == "json body"


def test_rerank_search_results_prefers_earlier_sections_when_other_signals_tie():
    docs, metas, _distances = rerank_engine.rerank_search_results(
        query="introduction",
        docs=["later body", "earlier body"],
        metas=[
            {"title": "Manual", "section_heading": "Overview", "section_index": 4, "section_count": 5},
            {"title": "Manual", "section_heading": "Overview", "section_index": 0, "section_count": 5},
        ],
        distances=[0.2, 0.2],
        normalize_topic=mcp_state._normalize_topic,
    )

    assert metas[0]["section_index"] == 0
    assert docs[0] == "earlier body"


def test_rerank_search_results_boosts_tabular_sources_for_table_queries():
    docs, metas, _distances = rerank_engine.rerank_search_results(
        query="excel table columns",
        docs=["html body", "xlsx body"],
        metas=[
            {"title": "Guide", "section_heading": "Reference", "source_kind": "html"},
            {"title": "report.xlsx", "section_heading": "Users / Row 1 - Alice | admin", "source_kind": "xlsx"},
        ],
        distances=[0.1, 0.18],
        normalize_topic=mcp_state._normalize_topic,
    )

    assert metas[0]["source_kind"] == "xlsx"
    assert docs[0] == "xlsx body"


def test_rerank_search_results_boosts_summary_sections_for_count_queries():
    docs, metas, _distances = rerank_engine.rerank_search_results(
        query="how many columns are in this table",
        docs=["row body", "summary body"],
        metas=[
            {"title": "report.xlsx", "section_heading": "Users / Row 1 - name=Alice | role=admin", "source_kind": "xlsx"},
            {"title": "report.xlsx", "section_heading": "Users / Summary", "source_kind": "xlsx"},
        ],
        distances=[0.1, 0.16],
        normalize_topic=mcp_state._normalize_topic,
    )

    assert metas[0]["section_heading"] == "Users / Summary"
    assert docs[0] == "summary body"


def test_rerank_search_results_boosts_markdown_code_sections_for_code_queries():
    docs, metas, _distances = rerank_engine.rerank_search_results(
        query="python api example",
        docs=["overview body", "code body"],
        metas=[
            {
                "title": "Guide",
                "section_heading": "Overview",
                "source_kind": "markdown",
                "section_level": 1,
                "has_code_block": False,
                "has_link_target": False,
            },
            {
                "title": "Guide",
                "section_heading": "API Example",
                "source_kind": "markdown",
                "section_level": 3,
                "has_code_block": True,
                "has_link_target": False,
            },
        ],
        distances=[0.1, 0.2],
        normalize_topic=mcp_state._normalize_topic,
    )

    assert metas[0]["has_code_block"] is True
    assert docs[0] == "code body"


def test_rerank_search_results_boosts_markdown_link_sections_for_reference_queries():
    docs, metas, _distances = rerank_engine.rerank_search_results(
        query="documentation url reference",
        docs=["plain body", "linked body"],
        metas=[
            {
                "title": "Guide",
                "section_heading": "Notes",
                "source_kind": "markdown",
                "section_level": 2,
                "has_code_block": False,
                "has_link_target": False,
            },
            {
                "title": "Guide",
                "section_heading": "Reference Links",
                "source_kind": "markdown",
                "section_level": 2,
                "has_code_block": False,
                "has_link_target": True,
            },
        ],
        distances=[0.1, 0.16],
        normalize_topic=mcp_state._normalize_topic,
    )

    assert metas[0]["has_link_target"] is True
    assert docs[0] == "linked body"


def test_resolve_rerank_strategy_routes_by_source_kind():
    assert rerank_engine._resolve_rerank_strategy("markdown").name == "narrative"
    assert rerank_engine._resolve_rerank_strategy("json").name == "narrative"
    assert rerank_engine._resolve_rerank_strategy("csv").name == "tabular"
    assert rerank_engine._resolve_rerank_strategy("xlsx").name == "tabular"
    assert rerank_engine._resolve_rerank_strategy("pdf").name == "pdf"


def test_resolve_rerank_strategy_uses_generic_fallback_for_unknown_format():
    assert rerank_engine._resolve_rerank_strategy("custom-format").name == "generic"


class _DeleteFakeRuntime:
    def __init__(self, payload):
        self.payload = payload
        self.calls: list[str] = []

    def remove_site_state(self, site_id: str):
        self.calls.append(site_id)
        return self.payload


class _DeleteFakeCollection:
    def __init__(self, metadatas):
        self._metadatas = metadatas
        self.deleted_where = None

    def get(self, where: dict[str, str], include: list[str]):
        assert include == ["metadatas"]
        return {"metadatas": self._metadatas if where.get("site_id") else []}

    def delete(self, where: dict[str, str]):
        self.deleted_where = where


def _catalog_service(collection, runtime, raw_path, state_path):
    return DocumentationCatalogService(
        ChromaDocumentationCatalogRepository(collection),
        runtime=runtime,
        site_raw_docs_path=raw_path,
        site_index_state_path=state_path,
    )


def test_delete_site_by_id_returns_busy_payload_without_chroma_delete(tmp_path):
    runtime = _DeleteFakeRuntime({"status": "busy", "site_id": "playwright-dev-docs", "active_job_ids": ["job-1"]})
    collection = _DeleteFakeCollection(metadatas=[{"site_id": "playwright-dev-docs"}])

    result = _catalog_service(
        collection,
        runtime,
        lambda _site_id: tmp_path / "unused.jsonl",
        lambda _site_id: tmp_path / "unused.state.json",
    ).delete_site(
        "playwright-dev-docs",
        delete_raw_files=True,
    )

    assert result["status"] == "busy"
    assert result["active_job_ids"] == ["job-1"]
    assert collection.deleted_where is None


def test_delete_site_by_id_returns_not_found_when_no_docs_no_state_no_files(tmp_path):
    runtime = _DeleteFakeRuntime(
        {
            "status": "ok",
            "site_id": "unknown-site",
            "deleted_jobs": 0,
            "deleted_routes": 0,
            "deleted_sync": False,
        }
    )
    collection = _DeleteFakeCollection(metadatas=[])

    result = _catalog_service(
        collection,
        runtime,
        lambda _site_id: tmp_path / "missing.jsonl",
        lambda _site_id: tmp_path / "missing.state.json",
    ).delete_site(
        "unknown-site",
        delete_raw_files=True,
    )

    assert result["status"] == "not_found"
    assert result["site_id"] == "unknown-site"
    assert result["deleted_docs"] == 0
    assert result["deleted_files"] == []
    assert collection.deleted_where == {"site_id": "unknown-site"}


def test_delete_site_by_id_deletes_docs_state_and_files(tmp_path):
    runtime = _DeleteFakeRuntime(
        {
            "status": "ok",
            "site_id": "playwright-dev-docs",
            "deleted_jobs": 2,
            "deleted_routes": 1,
            "deleted_sync": True,
        }
    )
    collection = _DeleteFakeCollection(metadatas=[{"site_id": "playwright-dev-docs"}, {"site_id": "playwright-dev-docs"}])

    raw_file = tmp_path / "playwright-dev-docs.jsonl"
    state_file = tmp_path / "playwright-dev-docs.state.json"
    raw_file.write_text("raw", encoding="utf-8")
    state_file.write_text("state", encoding="utf-8")

    result = _catalog_service(
        collection,
        runtime,
        lambda _site_id: raw_file,
        lambda _site_id: state_file,
    ).delete_site(
        "playwright-dev-docs",
        delete_raw_files=True,
    )

    assert result["status"] == "ok"
    assert result["site_id"] == "playwright-dev-docs"
    assert result["deleted_docs"] == 2
    assert result["deleted_jobs"] == 2
    assert result["deleted_routes"] == 1
    assert result["deleted_sync"] is True
    assert len(result["deleted_files"]) == 2
    assert collection.deleted_where == {"site_id": "playwright-dev-docs"}
    assert not raw_file.exists()
    assert not state_file.exists()


class _ListSitesCollection:
    def __init__(self, metadatas):
        self._metadatas = metadatas
        self.get_calls: list[dict[str, int | list[str]]] = []

    def count(self) -> int:
        return len(self._metadatas)

    def get(self, include: list[str], limit: int | None = None, offset: int = 0):
        assert include == ["metadatas"]
        if limit is None:
            self.get_calls.append({"offset": offset, "limit": len(self._metadatas), "include": include})
            return {"metadatas": self._metadatas}
        self.get_calls.append({"offset": offset, "limit": limit, "include": include})
        return {"metadatas": self._metadatas[offset : offset + limit]}


def test_list_sites_in_database_returns_counts_and_active_flags():
    collection = _ListSitesCollection(
        [
            {"site_id": "a-site", "site_name": "A Site"},
            {"site_id": "a-site", "site_name": "A Site"},
            {"site_id": "b-site", "site_name": "B Site"},
        ]
    )

    payload = _catalog_service(collection, None, lambda _site_id: None, lambda _site_id: None).list_sites(
        active_site_ids={"b-site"},
        include_active=True,
    )

    assert payload["status"] == "ok"
    assert payload["total_sites"] == 2
    assert payload["returned_sites"] == 2
    assert payload["items"] == [
        {
            "site_id": "a-site",
            "site_name": "A Site",
            "document_count": 2,
            "is_active_ingestion": False,
        },
        {
            "site_id": "b-site",
            "site_name": "B Site",
            "document_count": 1,
            "is_active_ingestion": True,
        },
    ]


def test_fetch_all_metadatas_uses_pagination_to_avoid_large_single_query():
    metadatas = [{"site_id": f"site-{idx}", "site_name": f"Site {idx}"} for idx in range(1200)]
    collection = _ListSitesCollection(metadatas)

    payload = _catalog_service(collection, None, lambda _site_id: None, lambda _site_id: None).list_sites(
        active_site_ids=set(),
        include_active=True,
    )

    assert payload["status"] == "ok"
    assert payload["total_sites"] == 1200
    assert len(collection.get_calls) == 3
    assert collection.get_calls[0]["offset"] == 0
    assert collection.get_calls[0]["limit"] == 500
    assert collection.get_calls[1]["offset"] == 500
    assert collection.get_calls[1]["limit"] == 500
    assert collection.get_calls[2]["offset"] == 1000
    assert collection.get_calls[2]["limit"] == 500


def test_list_sites_in_database_can_hide_active_sites():
    collection = _ListSitesCollection(
        [
            {"site_id": "a-site", "site_name": "A Site"},
            {"site_id": "b-site", "site_name": "B Site"},
        ]
    )

    payload = _catalog_service(collection, None, lambda _site_id: None, lambda _site_id: None).list_sites(
        active_site_ids={"b-site"},
        include_active=False,
    )

    assert payload["status"] == "ok"
    assert payload["total_sites"] == 2
    assert payload["returned_sites"] == 1
    assert payload["items"] == [
        {
            "site_id": "a-site",
            "site_name": "A Site",
            "document_count": 1,
            "is_active_ingestion": False,
        }
    ]



def test_list_sites_in_database_includes_active_site_without_indexed_docs():
    collection = _ListSitesCollection(metadatas=[])

    payload = _catalog_service(collection, None, lambda _site_id: None, lambda _site_id: None).list_sites(
        active_site_ids={"active-site"},
        include_active=True,
    )

    assert payload["status"] == "ok"
    assert payload["total_sites"] == 1
    assert payload["returned_sites"] == 1
    assert payload["items"] == [
        {
            "site_id": "active-site",
            "site_name": "active-site",
            "document_count": 0,
            "is_active_ingestion": True,
        }
    ]

def test_list_sites_in_database_returns_empty_payload_when_no_site_found():
    collection = _ListSitesCollection(metadatas=[])

    payload = _catalog_service(collection, None, lambda _site_id: None, lambda _site_id: None).list_sites(
        active_site_ids=set(),
        include_active=True,
    )

    assert payload == {
        "status": "ok",
        "total_sites": 0,
        "returned_sites": 0,
        "items": [],
        "message": "No documentation sites found in database.",
    }
