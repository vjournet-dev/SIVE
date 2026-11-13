from sive.domain.core.sites import SiteDefinition
from sive.domain.runtime_state.runtime import IngestRuntime
from sive.domain.runtime_state.state import IngestJobRecord, SiteSyncRecord, TopicRouteRecord


class _FakeCollection:
    pass


def _job(job_id: str, site_id: str, status: str) -> IngestJobRecord:
    return IngestJobRecord(
        job_id=job_id,
        site_id=site_id,
        site_name=site_id,
        start_url=f"https://{site_id}/docs/intro",
        allowed_host=site_id,
        allowed_path_prefix="/docs/",
        status=status,
        phase="running" if status in {"queued", "running"} else "completed",
        created_at="2026-01-01T00:00:00+00:00",
        incremental=True,
        max_pages=100,
        delay=0.2,
    )


def _route(topic_key: str, site_id: str) -> TopicRouteRecord:
    return TopicRouteRecord(
        topic=topic_key,
        topic_key=topic_key,
        site_id=site_id,
        site_name=site_id,
        start_url=f"https://{site_id}/docs/intro",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


def _sync(site_id: str) -> SiteSyncRecord:
    return SiteSyncRecord(
        site_id=site_id,
        site_name=site_id,
        start_url=f"https://{site_id}/docs/intro",
        allowed_host=site_id,
        allowed_path_prefix="/docs/",
    )


def test_remove_site_state_returns_busy_when_job_active(tmp_path):
    runtime = IngestRuntime(
        collection=_FakeCollection(),
        jobs_state_path=tmp_path / "jobs.json",
        routes_state_path=tmp_path / "routes.json",
        sync_state_path=tmp_path / "sync.json",
        collection_name="docs",
        embedding_model_name="sentence-transformers/all-MiniLM-L6-v2",
    )
    runtime.jobs = {
        "active": _job("active", "playwright-dev-docs", "running"),
    }

    result = runtime.remove_site_state("playwright-dev-docs")

    assert result["status"] == "busy"
    assert result["site_id"] == "playwright-dev-docs"
    assert result["active_job_ids"] == ["active"]


def test_remove_site_state_cleans_jobs_routes_and_sync(tmp_path):
    runtime = IngestRuntime(
        collection=_FakeCollection(),
        jobs_state_path=tmp_path / "jobs.json",
        routes_state_path=tmp_path / "routes.json",
        sync_state_path=tmp_path / "sync.json",
        collection_name="docs",
        embedding_model_name="sentence-transformers/all-MiniLM-L6-v2",
    )
    runtime.jobs = {
        "target-job": _job("target-job", "playwright-dev-docs", "succeeded"),
        "other-job": _job("other-job", "other-site", "succeeded"),
    }
    runtime.routes = {
        "playwright": _route("playwright", "playwright-dev-docs"),
        "other": _route("other", "other-site"),
    }
    runtime.site_sync = {
        "playwright-dev-docs": _sync("playwright-dev-docs"),
        "other-site": _sync("other-site"),
    }

    result = runtime.remove_site_state("playwright-dev-docs")

    assert result["status"] == "ok"
    assert result["deleted_jobs"] == 1
    assert result["deleted_routes"] == 1
    assert result["deleted_sync"] is True

    assert "target-job" not in runtime.jobs
    assert "other-job" in runtime.jobs
    assert "playwright" not in runtime.routes
    assert "other" in runtime.routes
    assert "playwright-dev-docs" not in runtime.site_sync
    assert "other-site" in runtime.site_sync


def test_remove_site_state_returns_ok_when_site_unknown(tmp_path):
    runtime = IngestRuntime(
        collection=_FakeCollection(),
        jobs_state_path=tmp_path / "jobs.json",
        routes_state_path=tmp_path / "routes.json",
        sync_state_path=tmp_path / "sync.json",
        collection_name="docs",
        embedding_model_name="sentence-transformers/all-MiniLM-L6-v2",
    )

    result = runtime.remove_site_state("unknown-site")

    assert result == {
        "status": "ok",
        "site_id": "unknown-site",
        "deleted_jobs": 0,
        "deleted_routes": 0,
        "deleted_sync": False,
    }


def test_topic_route_accumulates_sites_and_removes_only_target_reference(tmp_path):
    runtime = IngestRuntime(
        collection=_FakeCollection(),
        jobs_state_path=tmp_path / "jobs.json",
        routes_state_path=tmp_path / "routes.json",
        sync_state_path=tmp_path / "sync.json",
        collection_name="docs",
        embedding_model_name="sentence-transformers/all-MiniLM-L6-v2",
    )
    first = SiteDefinition("site-a", "Site A", "https://a.example/docs", "a.example", "/docs/")
    second = SiteDefinition("site-b", "Site B", "https://b.example/docs", "b.example", "/docs/")

    runtime.update_topic_route(topic="Shared", topic_key="shared", site=first)
    runtime.update_topic_route(topic="Shared", topic_key="shared", site=second)

    assert runtime.routes["shared"].site_ids == ("site-a", "site-b")
    result = runtime.remove_site_state("site-a")
    assert result["deleted_routes"] == 1
    assert runtime.routes["shared"].site_ids == ("site-b",)
