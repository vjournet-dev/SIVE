import json
from datetime import UTC, datetime

from sive.domain.runtime_state import state as mcp_state


def test_sync_from_dict_parses_expected_fields():
    raw = {
        "site_id": "redux-toolkit-js-org-introduction",
        "site_name": "redux-toolkit.js.org",
        "start_url": "https://redux-toolkit.js.org/introduction/getting-started",
        "allowed_host": "redux-toolkit.js.org",
        "allowed_path_prefix": "/introduction/",
        "last_job_id": "job-123",
        "last_status": "succeeded",
        "last_scrape_started_at": "2026-07-13T10:00:00+00:00",
        "last_scrape_finished_at": "2026-07-13T10:01:00+00:00",
        "last_successful_scrape_at": "2026-07-13T10:01:00+00:00",
        "last_indexed_at": "2026-07-13T10:01:00+00:00",
        "last_pages_scraped": 42,
        "last_indexed_chunks": 120,
        "updated_at": "2026-07-13T10:01:00+00:00",
        "start_urls": [
            "https://redux-toolkit.js.org/introduction/getting-started",
            "https://redux-toolkit.js.org/api/",
        ],
        "allowed_path_prefixes": ["/introduction/", "/api/"],
    }

    sync = mcp_state._sync_from_dict(raw)

    assert sync is not None
    assert sync.site_id == "redux-toolkit-js-org-introduction"
    assert sync.last_status == "succeeded"
    assert sync.last_pages_scraped == 42
    assert sync.last_indexed_chunks == 120
    assert sync.start_urls[-1] == "https://redux-toolkit.js.org/api/"
    assert sync.allowed_path_prefixes == ("/introduction/", "/api/")


def test_write_then_read_site_sync_state_roundtrip(tmp_path):
    state_path = tmp_path / "site_sync_state.json"
    initial = {
        "redux-toolkit-js-org-introduction": mcp_state.SiteSyncRecord(
            site_id="redux-toolkit-js-org-introduction",
            site_name="redux-toolkit.js.org",
            start_url="https://redux-toolkit.js.org/introduction/getting-started",
            allowed_host="redux-toolkit.js.org",
            allowed_path_prefix="/introduction/",
            last_job_id="job-123",
            last_status="succeeded",
            last_scrape_started_at="2026-07-13T10:00:00+00:00",
            last_scrape_finished_at="2026-07-13T10:01:00+00:00",
            last_successful_scrape_at="2026-07-13T10:01:00+00:00",
            last_indexed_at="2026-07-13T10:01:00+00:00",
            last_pages_scraped=42,
            last_indexed_chunks=120,
            updated_at="2026-07-13T10:01:00+00:00",
            start_urls=(
                "https://redux-toolkit.js.org/introduction/getting-started",
                "https://redux-toolkit.js.org/api/",
            ),
            allowed_path_prefixes=("/introduction/", "/api/"),
        )
    }

    mcp_state._write_site_sync_state(state_path, initial)
    loaded = mcp_state._read_site_sync_state(state_path)

    assert "redux-toolkit-js-org-introduction" in loaded
    sync = loaded["redux-toolkit-js-org-introduction"]
    assert sync.last_status == "succeeded"
    assert sync.last_scrape_finished_at == "2026-07-13T10:01:00+00:00"
    assert sync.last_successful_scrape_at == "2026-07-13T10:01:00+00:00"
    assert sync.last_indexed_at == "2026-07-13T10:01:00+00:00"
    assert sync.start_urls[-1] == "https://redux-toolkit.js.org/api/"
    assert sync.allowed_path_prefixes == ("/introduction/", "/api/")


def test_sync_staleness_seconds_prefers_last_successful_scrape_timestamp():
    now = datetime(2026, 7, 13, 12, 0, 0, tzinfo=UTC)
    sync = mcp_state.SiteSyncRecord(
        site_id="redux-toolkit-js-org-introduction",
        site_name="redux-toolkit.js.org",
        start_url="https://redux-toolkit.js.org/introduction/getting-started",
        allowed_host="redux-toolkit.js.org",
        allowed_path_prefix="/introduction/",
        last_scrape_started_at="2026-07-13T10:00:00+00:00",
        last_scrape_finished_at="2026-07-13T10:30:00+00:00",
        last_successful_scrape_at="2026-07-13T11:00:00+00:00",
        updated_at="2026-07-13T11:01:00+00:00",
    )

    staleness = mcp_state._sync_staleness_seconds(sync, now=now)

    assert staleness == 3600


def test_rank_sync_records_by_staleness_prioritizes_unknown_first_then_oldest():
    now = datetime(2026, 7, 13, 12, 0, 0, tzinfo=UTC)
    unknown = mcp_state.SiteSyncRecord(
        site_id="unknown-site",
        site_name="Unknown",
        start_url="https://example.com/docs/intro",
        allowed_host="example.com",
        allowed_path_prefix="/docs/",
    )
    stale = mcp_state.SiteSyncRecord(
        site_id="stale-site",
        site_name="Stale",
        start_url="https://stale.dev/docs/intro",
        allowed_host="stale.dev",
        allowed_path_prefix="/docs/",
        last_successful_scrape_at="2026-07-11T12:00:00+00:00",
    )
    fresh = mcp_state.SiteSyncRecord(
        site_id="fresh-site",
        site_name="Fresh",
        start_url="https://fresh.dev/docs/intro",
        allowed_host="fresh.dev",
        allowed_path_prefix="/docs/",
        last_successful_scrape_at="2026-07-13T11:30:00+00:00",
    )

    ranked = mcp_state._rank_sync_records(
        [fresh, stale, unknown],
        sort_by="staleness",
        descending=True,
        now=now,
    )

    assert [entry.site_id for entry in ranked] == ["unknown-site", "stale-site", "fresh-site"]


def test_job_to_dict_promotes_result_metrics_to_top_level():
    job = mcp_state.IngestJobRecord(
        job_id="job-1",
        site_id="site-1",
        site_name="Site 1",
        start_url="https://example.com/docs",
        allowed_host="example.com",
        allowed_path_prefix="/docs",
        status="succeeded",
        phase="completed",
        created_at="2026-07-22T10:00:00+00:00",
        incremental=True,
        max_pages=1200,
        delay=0.2,
        progress_percent=100,
        result={
            "pages_scraped": 5,
            "indexed_chunks": 42,
            "changed_pages": 5,
            "removed_pages": 0,
            "skipped_pages": 0,
        },
    )

    payload = mcp_state._job_to_dict(job)

    assert payload["pages_scraped"] == 5
    assert payload["indexed_chunks"] == 42
    assert payload["changed_pages"] == 5
    assert payload["removed_pages"] == 0
    assert payload["skipped_pages"] == 0


def test_topic_route_v2_is_loaded_and_rewritten_as_v3(tmp_path):
    state_path = tmp_path / "topic_routes.json"
    state_path.write_text(
        json.dumps(
            {
                "version": 2,
                "routes": [
                    {
                        "topic": "Open XML",
                        "topic_key": "open xml",
                        "site_id": "openxml-guide",
                        "site_name": "Open XML Guide",
                        "start_url": "https://example.com/openxml/",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "updated_at": "2026-01-01T00:00:00+00:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    routes = mcp_state._read_topic_routes_state(state_path)

    assert routes["open xml"].site_ids == ("openxml-guide",)
    mcp_state._write_topic_routes_state(state_path, routes)
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["version"] == 3
    assert persisted["routes"][0]["sites"][0]["site_id"] == "openxml-guide"
    assert "site_id" not in persisted["routes"][0]
