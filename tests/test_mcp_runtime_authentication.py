from __future__ import annotations

from dataclasses import dataclass

from sive.domain.runtime_state import runtime as mcp_runtime
from sive.domain.runtime_state.state import IngestJobRecord


class _FakeCollection:
    pass


@dataclass
class _FakeIngestResult:
    site_id: str = "contoso-hosteddocs"
    site_name: str = "contoso.hosteddocs.com"
    pages_scraped: int = 3
    indexed_chunks: int = 7
    changed_pages: int = 3
    removed_pages: int = 0
    skipped_pages: int = 0
    duration_seconds: float = 1.2
    incremental: bool = True


def _make_runtime(tmp_path):
    return mcp_runtime.IngestRuntime(
        collection=_FakeCollection(),
        jobs_state_path=tmp_path / "jobs.json",
        routes_state_path=tmp_path / "routes.json",
        sync_state_path=tmp_path / "sync.json",
        collection_name="docs",
        embedding_model_name="sentence-transformers/all-MiniLM-L6-v2",
    )


def _job(job_id: str, status: str, phase: str) -> IngestJobRecord:
    return IngestJobRecord(
        job_id=job_id,
        site_id="contoso-hosteddocs",
        site_name="contoso.hosteddocs.com",
        start_url="https://contoso.hosteddocs.com/sites/engineering/docs",
        allowed_host="contoso.hosteddocs.com",
        allowed_path_prefix="/sites/engineering/",
        status=status,
        phase=phase,
        created_at="2026-07-23T10:00:00+00:00",
        incremental=True,
        max_pages=10,
        delay=0.0,
    )


def test_run_ingest_job_sets_awaiting_authentication_when_login_is_detected(tmp_path, monkeypatch):
    runtime = _make_runtime(tmp_path)
    runtime.jobs["job-auth"] = _job("job-auth", status="queued", phase="queued")

    def _raise_auth_required(*args, **kwargs):
        raise mcp_runtime.AuthenticationRequiredError(
            "Authentication is required to access this documentation site.",
            login_url="https://contoso.hosteddocs.com/login",
        )

    monkeypatch.setattr(mcp_runtime, "run_ingest_for_site", _raise_auth_required)

    runtime._run_ingest_job("job-auth")

    stored = runtime.get_job("job-auth")
    assert stored is not None
    assert stored.status == "awaiting_authentication"
    assert stored.phase == "awaiting_authentication"
    assert stored.needs_authentication is True
    assert stored.detected_login_url == "https://contoso.hosteddocs.com/login"


def test_authenticate_ingest_job_captures_cookies_and_resumes(tmp_path, monkeypatch):
    runtime = _make_runtime(tmp_path)
    job = _job("job-auth", status="awaiting_authentication", phase="awaiting_authentication")
    job.needs_authentication = True
    job.detected_login_url = "https://contoso.hosteddocs.com/login"
    runtime.jobs[job.job_id] = job

    monkeypatch.setattr(
        mcp_runtime,
        "capture_authenticated_session",
        lambda **kwargs: {"cookies": {"session": "token-value"}, "headers": {}},
    )

    captured_auth_session = {}

    def _run_ingest_for_site_with_capture(*args, **kwargs):
        captured_auth_session.update(kwargs.get("auth_session") or {})
        return _FakeIngestResult()

    monkeypatch.setattr(mcp_runtime, "run_ingest_for_site", _run_ingest_for_site_with_capture)

    class _ImmediateThread:
        def __init__(self, target, args=(), daemon=False):
            self._target = target
            self._args = args
            self._alive = False

        def start(self):
            self._alive = True
            self._target(*self._args)
            self._alive = False

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return self._alive

    monkeypatch.setattr(mcp_runtime.threading, "Thread", _ImmediateThread)

    payload = runtime.authenticate_ingest_job(job_id="job-auth", timeout_seconds=5)

    assert payload["status"] == "authentication_captured"
    assert payload["job_id"] == "job-auth"
    assert captured_auth_session == {"cookies": {"session": "token-value"}, "headers": {}}

    stored = runtime.get_job("job-auth")
    assert stored is not None
    assert stored.status == "succeeded"
    assert stored.needs_authentication is False


def test_set_ingest_auth_session_resumes_with_cookie_and_header_payload(tmp_path, monkeypatch):
    runtime = _make_runtime(tmp_path)
    job = _job("job-auth", status="awaiting_authentication", phase="awaiting_authentication")
    job.needs_authentication = True
    runtime.jobs[job.job_id] = job

    captured_auth_session = {}

    def _run_ingest_for_site_with_capture(*args, **kwargs):
        captured_auth_session.update(kwargs.get("auth_session") or {})
        return _FakeIngestResult()

    monkeypatch.setattr(mcp_runtime, "run_ingest_for_site", _run_ingest_for_site_with_capture)

    class _ImmediateThread:
        def __init__(self, target, args=(), daemon=False):
            self._target = target
            self._args = args

        def start(self):
            self._target(*self._args)

    monkeypatch.setattr(mcp_runtime.threading, "Thread", _ImmediateThread)

    payload = runtime.set_ingest_auth_session(
        job_id="job-auth",
        cookies={"sessionid": "abc"},
        headers={"Authorization": "Bearer token"},
    )

    assert payload["status"] == "authentication_session_set"
    assert captured_auth_session == {
        "cookies": {"sessionid": "abc"},
        "headers": {"Authorization": "Bearer token"},
    }

    stored = runtime.get_job("job-auth")
    assert stored is not None
    assert stored.status == "succeeded"


def test_authenticate_ingest_job_accepts_header_only_session(tmp_path, monkeypatch):
    runtime = _make_runtime(tmp_path)
    job = _job("job-auth", status="awaiting_authentication", phase="awaiting_authentication")
    job.needs_authentication = True
    runtime.jobs[job.job_id] = job

    monkeypatch.setattr(
        mcp_runtime,
        "capture_authenticated_session",
        lambda **kwargs: {"cookies": {}, "headers": {"Authorization": "Bearer token"}},
    )

    captured_auth_session = {}

    def _run_ingest_for_site_with_capture(*args, **kwargs):
        captured_auth_session.update(kwargs.get("auth_session") or {})
        return _FakeIngestResult()

    monkeypatch.setattr(mcp_runtime, "run_ingest_for_site", _run_ingest_for_site_with_capture)

    class _ImmediateThread:
        def __init__(self, target, args=(), daemon=False):
            self._target = target
            self._args = args
            self._alive = False

        def start(self):
            self._alive = True
            self._target(*self._args)
            self._alive = False

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return self._alive

    monkeypatch.setattr(mcp_runtime.threading, "Thread", _ImmediateThread)

    payload = runtime.authenticate_ingest_job(job_id="job-auth", timeout_seconds=5)

    assert payload["status"] == "authentication_captured"
    assert captured_auth_session == {"cookies": {}, "headers": {"Authorization": "Bearer token"}}


def test_set_ingest_auth_config_resumes_with_oauth_config(tmp_path, monkeypatch):
    runtime = _make_runtime(tmp_path)
    job = _job("job-auth", status="awaiting_authentication", phase="awaiting_authentication")
    job.needs_authentication = True
    runtime.jobs[job.job_id] = job

    monkeypatch.setattr(
        mcp_runtime.IngestRuntime,
        "_capture_authenticated_session_threadsafe",
        lambda self, **kwargs: {"cookies": {}, "headers": {"Authorization": "Bearer cfg-token"}},
    )

    captured_auth_session = {}

    def _run_ingest_for_site_with_capture(*args, **kwargs):
        captured_auth_session.update(kwargs.get("auth_session") or {})
        return _FakeIngestResult()

    monkeypatch.setattr(mcp_runtime, "run_ingest_for_site", _run_ingest_for_site_with_capture)

    class _ImmediateThread:
        def __init__(self, target, args=(), daemon=False):
            self._target = target
            self._args = args

        def start(self):
            self._target(*self._args)

    monkeypatch.setattr(mcp_runtime.threading, "Thread", _ImmediateThread)

    payload = runtime.set_ingest_auth_config(
        job_id="job-auth",
        auth_config={"type": "oauth", "token": "cfg-token"},
        timeout_seconds=5,
    )

    assert payload["status"] == "authentication_config_applied"
    assert captured_auth_session == {
        "cookies": {},
        "headers": {"Authorization": "Bearer cfg-token"},
    }


def test_run_ingest_job_tracks_index_counters_from_progress_callback(tmp_path, monkeypatch):
    runtime = _make_runtime(tmp_path)
    runtime.jobs["job-progress"] = _job("job-progress", status="queued", phase="queued")

    def _run_ingest_for_site_with_progress(*args, **kwargs):
        progress_callback = kwargs.get("progress_callback")
        assert callable(progress_callback)
        progress_callback({"phase": "crawl", "visited": 3, "queued": 1, "pages_kept": 3})
        progress_callback(
            {
                "phase": "index",
                "visited": 3,
                "queued": 0,
                "pages_kept": 3,
                "index_done": 2,
                "index_total": 5,
            }
        )
        return _FakeIngestResult(indexed_chunks=7)

    monkeypatch.setattr(mcp_runtime, "run_ingest_for_site", _run_ingest_for_site_with_progress)

    runtime._run_ingest_job("job-progress")

    stored = runtime.get_job("job-progress")
    assert stored is not None
    assert stored.status == "succeeded"
    assert stored.index_done == 7
    assert stored.index_total == 7


def test_run_ingest_job_progress_uses_live_crawl_queue(tmp_path, monkeypatch):
    runtime = _make_runtime(tmp_path)
    job = _job("job-progress", status="queued", phase="queued")
    job.max_pages = 1200
    runtime.jobs[job.job_id] = job
    observed_percentages: list[int] = []

    def _run_ingest_for_site_with_progress(*args, **kwargs):
        progress_callback = kwargs.get("progress_callback")
        assert callable(progress_callback)
        for event in (
            {"phase": "crawl", "visited": 1, "queued": 9, "pages_kept": 1},
            {"phase": "crawl", "visited": 5, "queued": 5, "pages_kept": 5},
            {"phase": "crawl", "visited": 10, "queued": 0, "pages_kept": 10},
            {
                "phase": "index",
                "visited": 10,
                "queued": 0,
                "pages_kept": 10,
                "index_done": 0,
                "index_total": 10,
            },
            {
                "phase": "index",
                "visited": 10,
                "queued": 0,
                "pages_kept": 10,
                "index_done": 5,
                "index_total": 10,
            },
        ):
            progress_callback(event)
            stored = runtime.get_job(job.job_id)
            assert stored is not None
            observed_percentages.append(stored.progress_percent)
        return _FakeIngestResult(indexed_chunks=10)

    monkeypatch.setattr(mcp_runtime, "run_ingest_for_site", _run_ingest_for_site_with_progress)

    runtime._run_ingest_job(job.job_id)

    assert observed_percentages == [9, 45, 90, 90, 94]


