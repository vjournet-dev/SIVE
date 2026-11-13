import json

from sive.app.mcp_server import tools_ingest as mcp_tools_ingest
from sive.domain.core import sites as domain_sites
from sive.domain.core.sites import SiteDefinition
from sive.domain.ingest import input_resolution


class _FakeServer:
    def __init__(self):
        self.tools: dict[str, object] = {}

    def tool(self):
        def _decorator(func):
            self.tools[func.__name__] = func
            return func

        return _decorator


class _FakeRuntime:
    def enqueue_ingest_job(self, *_args, **_kwargs):
        raise AssertionError("enqueue_ingest_job should not be called when suggestions are unresolved")

    def update_topic_route(self, *_args, **_kwargs):
        raise AssertionError("update_topic_route should not be called in this test")


class _FakeRuntimeForUpdate:
    def __init__(self):
        self.collection = object()
        self.resolve_existing_site_calls: list[str] = []
        self.enqueued: list[dict[str, object]] = []

    def resolve_existing_site(self, site_id: str):
        self.resolve_existing_site_calls.append(site_id)
        if site_id == "docs-site":
            return SiteDefinition(
                site_id="docs-site",
                site_name="Docs",
                start_url="https://example.com/docs/intro",
                allowed_host="example.com",
                allowed_path_prefix="/docs/",
            )
        return None

    def enqueue_ingest_job(self, site: SiteDefinition, *, incremental: bool, max_pages: int, delay: float):
        payload = {
            "status": "queued",
            "job_id": "job-123",
            "site_id": site.site_id,
            "incremental": incremental,
            "max_pages": max_pages,
            "delay": delay,
        }
        self.enqueued.append(payload)
        return payload

    def update_topic_route(self, *_args, **_kwargs):
        return None


class _FakeRuntimeForIngest:
    def __init__(self):
        self.enqueued_site: SiteDefinition | None = None

    def enqueue_ingest_job(self, site: SiteDefinition, **_kwargs):
        self.enqueued_site = site
        return {
            "status": "queued",
            "job_id": "job-openxml",
            "site_id": site.site_id,
            "start_urls": list(site.crawl_start_urls),
            "allowed_path_prefixes": list(site.crawl_path_prefixes),
        }

    def update_topic_route(self, *_args, **_kwargs):
        return None


def test_ingest_tool_returns_invalid_local_path_for_missing_local_path_without_web_suggestion():
    server = _FakeServer()
    runtime = _FakeRuntime()
    captured: dict[str, object] = {}

    def _search_doc_urls_on_web(query: str, max_results: int):
        captured["query"] = query
        captured["max_results"] = max_results
        return []

    def _resolve_ingest_input(value: str, max_suggestions: int):
        return input_resolution.resolve_ingest_input(
            value,
            search_doc_urls_on_web=_search_doc_urls_on_web,
            max_suggestions=max_suggestions,
        )

    mcp_tools_ingest.register_ingest_tools(
        server,
        runtime=runtime,
        format_json=lambda payload: str(payload),
        normalize_topic=lambda value: value.strip().lower(),
        site_from_url=lambda _url: (_ for _ in ()).throw(AssertionError("site_from_url should not be called")),
        site_from_local_path=lambda _path: (_ for _ in ()).throw(AssertionError("site_from_local_path should not be called")),
        validate_ingest_start_url=lambda _url: None,
        resolve_ingest_input=_resolve_ingest_input,
    )

    ingest = server.tools["ingest"]
    result = ingest(url="./docs/missing-manual")

    assert "'status': 'invalid_local_path'" in result
    assert "'path': './docs/missing-manual'" in result
    assert captured == {}


def test_ingest_tool_queues_multiple_url_branches_as_one_site():
    server = _FakeServer()
    runtime = _FakeRuntimeForIngest()
    primary_url = "https://learn.microsoft.com/en-us/office/open-xml/"
    api_url = "https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml"

    mcp_tools_ingest.register_ingest_tools(
        server,
        runtime=runtime,
        format_json=json.dumps,
        normalize_topic=lambda value: value.strip().lower(),
        site_from_url=domain_sites.site_from_url,
        site_from_local_path=domain_sites.site_from_local_path,
        validate_ingest_start_url=lambda _url: None,
        resolve_ingest_input=lambda value, _max: {
            "status": "resolved_url",
            "url": value,
            "input_kind": "url",
        },
        site_from_urls=domain_sites.site_from_urls,
    )

    ingest = server.tools["ingest"]
    payload = json.loads(
        ingest(
            url=primary_url,
            additional_urls=[api_url],
            allowed_url_prefixes=[primary_url, api_url],
            site_id="openxml",
            site_name="Open XML",
        )
    )

    assert payload["status"] == "queued"
    assert payload["site_id"] == "openxml"
    assert payload["start_urls"] == [primary_url, api_url]
    assert runtime.enqueued_site is not None
    assert runtime.enqueued_site.crawl_path_prefixes == (
        "/en-us/office/open-xml/",
        "/en-us/dotnet/api/documentformat.openxml/",
    )


def test_update_documentation_source_site_id_delegates_to_differential_update():
    server = _FakeServer()
    runtime = _FakeRuntimeForUpdate()

    mcp_tools_ingest.register_ingest_tools(
        server,
        runtime=runtime,
        format_json=lambda payload: json.dumps(payload),
        normalize_topic=lambda value: value.strip().lower(),
        site_from_url=lambda _url: (_ for _ in ()).throw(AssertionError("site_from_url should not be called")),
        site_from_local_path=lambda _path: (_ for _ in ()).throw(AssertionError("site_from_local_path should not be called")),
        validate_ingest_start_url=lambda _url: None,
        resolve_ingest_input=lambda _value, _max: (_ for _ in ()).throw(AssertionError("resolve_ingest_input should not be called")),
    )

    update_source = server.tools["update_documentation_source"]
    payload = json.loads(update_source(target="docs-site", max_pages=200, delay=0.1))

    assert payload["status"] == "queued"
    assert payload["mode"] == "differential_update"
    assert payload["target_kind"] == "site_id"
    assert payload["target"] == "docs-site"
    assert payload["site_id"] == "docs-site"
    assert payload["progress_percent"] == 0
    assert payload["progress_bar"].endswith("0%")
    assert runtime.resolve_existing_site_calls == ["docs-site"]
    assert runtime.enqueued and runtime.enqueued[0]["incremental"] is True


def test_update_documentation_source_local_path_calls_selective_updater(tmp_path, monkeypatch):
    server = _FakeServer()
    runtime = _FakeRuntimeForUpdate()
    local_file = tmp_path / "docs" / "guide.md"
    local_file.parent.mkdir(parents=True)
    local_file.write_text("# Guide\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def _fake_update_existing_local_site(target_path: str, *, collection: object, **kwargs):
        captured["target_path"] = target_path
        captured["collection"] = collection
        return {
            "status": "ok",
            "mode": "local_selective_update",
            "checked": 1,
            "matched": 1,
            "updated": 1,
            "skipped": 0,
            "collision_count": 0,
            "progress_percent": 100,
            "progress_bar": "[####################] 100%",
        }

    monkeypatch.setattr(mcp_tools_ingest, "update_existing_local_site", _fake_update_existing_local_site)

    mcp_tools_ingest.register_ingest_tools(
        server,
        runtime=runtime,
        format_json=lambda payload: json.dumps(payload),
        normalize_topic=lambda value: value.strip().lower(),
        site_from_url=lambda _url: (_ for _ in ()).throw(AssertionError("site_from_url should not be called")),
        site_from_local_path=lambda _path: (_ for _ in ()).throw(AssertionError("site_from_local_path should not be called")),
        validate_ingest_start_url=lambda _url: None,
        resolve_ingest_input=lambda _value, _max: (_ for _ in ()).throw(AssertionError("resolve_ingest_input should not be called")),
    )

    update_source = server.tools["update_documentation_source"]
    payload = json.loads(update_source(target=str(local_file)))

    assert payload["status"] == "ok"
    assert payload["target_kind"] == "local_path"
    assert payload["progress_percent"] == 100
    assert payload["progress_bar"].endswith("100%")
    assert captured["target_path"] == str(local_file.resolve())
    assert captured["collection"] is runtime.collection
    assert runtime.resolve_existing_site_calls == []


def test_update_documentation_source_missing_local_path_returns_no_match():
    server = _FakeServer()
    runtime = _FakeRuntimeForUpdate()

    mcp_tools_ingest.register_ingest_tools(
        server,
        runtime=runtime,
        format_json=lambda payload: json.dumps(payload),
        normalize_topic=lambda value: value.strip().lower(),
        site_from_url=lambda _url: (_ for _ in ()).throw(AssertionError("site_from_url should not be called")),
        site_from_local_path=lambda _path: (_ for _ in ()).throw(AssertionError("site_from_local_path should not be called")),
        validate_ingest_start_url=lambda _url: None,
        resolve_ingest_input=lambda _value, _max: (_ for _ in ()).throw(AssertionError("resolve_ingest_input should not be called")),
    )

    update_source = server.tools["update_documentation_source"]
    payload = json.loads(update_source(target="./missing-folder/doc.md"))

    assert payload["status"] == "no_match"
    assert payload["target_kind"] == "local_path"
    assert payload["matched"] == 0
    assert payload["updated"] == 0
    assert payload["progress_percent"] == 100
    assert payload["progress_bar"].endswith("100%")
    assert runtime.resolve_existing_site_calls == []
