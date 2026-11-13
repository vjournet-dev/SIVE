from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from sive.app.mcp_server import build_server

TARGET_URL = "https://buildmedia.readthedocs.org/media/pdf/pymupdf/latest/pymupdf.pdf"
TARGET_TOPIC = "pymupdf"

REQUIRED_TOOLS = {
    "list_indexed_doc_sites",
    "list_documentation_sites_in_database",
    "get_site_sync_status",
    "list_site_sync_status",
    "delete_documentation_site",
    "ingest_status",
    "wait_for_ingest_completion",
    "authenticate_ingest_job",
    "search_documentation",
    "suggest_documentation_urls",
    "ingest",
    "ingest_and_register_topic",
    "update_site_differential",
}


def _extract_result_text(raw):
    # MCP v2 may return a CallToolResult object with structured content.
    structured = getattr(raw, "structured_content", None)
    if isinstance(structured, dict) and "result" in structured:
        return structured["result"]

    structured_legacy = getattr(raw, "structuredContent", None)
    if isinstance(structured_legacy, dict) and "result" in structured_legacy:
        return structured_legacy["result"]

    content = getattr(raw, "content", None)
    if isinstance(content, list) and content:
        first_block = content[0]
        text = getattr(first_block, "text", None)
        if isinstance(text, str):
            return text

    if isinstance(raw, tuple):
        if len(raw) > 1 and isinstance(raw[1], dict) and "result" in raw[1]:
            return raw[1]["result"]
        first = raw[0] if raw else None
        if isinstance(first, list) and first:
            block0 = first[0]
            text = getattr(block0, "text", None)
            if isinstance(text, str):
                return text
    if isinstance(raw, dict) and "result" in raw:
        return raw["result"]
    if isinstance(raw, str):
        return raw
    return str(raw)


def _parse_tool_result(raw):
    text = _extract_result_text(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def _call(server, name, args):
    raw = await server.call_tool(name, args)
    return _parse_tool_result(raw)


def _visible_sites_from_list_indexed_doc_sites(payload: str) -> set[str]:
    """Parse only visible site ids from bullet lines.

    The tool may also print: "Temporarily hidden while ingesting: ...".
    Those site ids are hidden and MUST NOT be treated as visible.
    """
    visible: set[str] = set()
    for line in payload.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        if "(" not in stripped or ")" not in stripped:
            continue
        site_id = stripped.rsplit("(", 1)[1].rstrip(")").strip()
        if site_id:
            visible.add(site_id)
    return visible


async def _wait_active_observation(server, job_id: str, site_id: str, timeout_seconds: float = 30.0):
    deadline = time.monotonic() + timeout_seconds
    last_status = None
    while time.monotonic() < deadline:
        status_now = await _call(server, "ingest_status", {"job_id": job_id})
        if not isinstance(status_now, dict):
            raise TypeError(f"STEP 8 KO ingest_status returned non-dict: {status_now}")
        lifecycle = status_now.get("status")
        last_status = lifecycle
        if lifecycle in {"queued", "running"}:
            listing = await _call(server, "list_indexed_doc_sites", {})
            if not isinstance(listing, str):
                raise RuntimeError(f"STEP 8 KO list_indexed_doc_sites non-string: {listing}")
            visible_sites = _visible_sites_from_list_indexed_doc_sites(listing)
            if site_id in visible_sites:
                raise RuntimeError("STEP 8 KO active site is visible in list_indexed_doc_sites bullet list")

            all_sites = await _call(server, "list_documentation_sites_in_database", {"include_active": True})
            if not isinstance(all_sites, dict):
                raise RuntimeError(f"STEP 8 KO list_documentation_sites_in_database non-dict: {all_sites}")
            match = None
            for item in all_sites.get("items", []):
                if isinstance(item, dict) and str(item.get("site_id", "")) == site_id:
                    match = item
                    break
            if match is None:
                raise RuntimeError(
                    "STEP 8 KO active site missing from list_documentation_sites_in_database(include_active=True)"
                )
            if match.get("is_active_ingestion") is not True:
                raise RuntimeError(f"STEP 8 KO active site flag is not true: {match}")

            global_search = await _call(server, "search_documentation", {"query": "PyMuPDF"})
            if not isinstance(global_search, str):
                raise RuntimeError(f"STEP 8 KO global search returned non-string: {global_search}")

            site_search = await _call(server, "search_documentation", {"query": "PyMuPDF", "site_id": site_id})
            if not isinstance(site_search, str):
                raise RuntimeError(f"STEP 8 KO site search returned non-string: {site_search}")
            lowered = site_search.lower()
            if "currently being ingested" not in lowered and "wait" not in lowered:
                raise RuntimeError(f"STEP 8 KO expected busy/wait message for active site, got: {site_search}")
            return

        await asyncio.sleep(0.5)

    raise RuntimeError(
        f"STEP 8 KO could not observe active state within timeout. Last observed status={last_status!r}"
    )


async def main() -> None:
    print("STEP 5 - MCP tool surface")
    s = build_server()
    names = set(getattr(s._tool_manager, "_tools", {}).keys())
    missing = sorted(REQUIRED_TOOLS - names)
    if missing:
        raise RuntimeError(f"STEP 5 KO missing tools: {missing}")
    print("STEP 5 OK")

    print("STEP 6 - URL guardrail 404")
    invalid = await _call(s, "ingest", {"url": "https://docs.python.org/this-page-does-not-exist"})
    if not isinstance(invalid, dict):
        raise TypeError(f"STEP 6 KO unexpected payload type: {type(invalid).__name__}")
    if invalid.get("status") != "invalid_start_url":
        raise RuntimeError(f"STEP 6 KO status expected invalid_start_url got {invalid}")
    if invalid.get("error_code") != "url_not_found_404":
        raise RuntimeError(f"STEP 6 KO error_code expected url_not_found_404 got {invalid}")
    if int(invalid.get("http_status", 0)) != 404:
        raise RuntimeError(f"STEP 6 KO http_status expected 404 got {invalid}")
    print("STEP 6 OK")

    print("STEP 7 - Start ingestion and register topic")
    started = await _call(
        s,
        "ingest_and_register_topic",
        {"topic": TARGET_TOPIC, "url": TARGET_URL, "incremental": True, "max_pages": 1200, "delay": 0.2},
    )
    if not isinstance(started, dict):
        raise TypeError(f"STEP 7 KO unexpected payload type: {type(started).__name__}")
    if not started.get("job_id"):
        raise RuntimeError(f"STEP 7 KO missing job_id: {started}")
    if started.get("route_registered") is not True:
        raise RuntimeError(f"STEP 7 KO route_registered expected true: {started}")
    job_id = str(started["job_id"])
    site_id = str(started.get("site_id", "")).strip()
    if not site_id:
        raise RuntimeError(f"STEP 7 KO missing site_id: {started}")
    print(f"STEP 7 OK job_id={job_id} site_id={site_id}")

    print("STEP 8 - Active ingestion behavior checks")
    await _wait_active_observation(s, job_id, site_id)
    print("STEP 8 OK")

    print("STEP 9 - wait_for_ingest_completion")
    waited = await _call(s, "wait_for_ingest_completion", {"job_id": job_id})
    if not isinstance(waited, dict):
        raise TypeError(f"STEP 9 KO wait response non-dict: {waited}")
    if waited.get("status") not in {"succeeded", "failed"}:
        raise RuntimeError(f"STEP 9 KO terminal status expected succeeded|failed: {waited}")
    for key in ("progress_percent", "phase", "visited_urls", "pages_kept", "queued_urls"):
        if key not in waited:
            raise RuntimeError(f"STEP 9 KO missing progress field {key}: {waited}")
    print(f"STEP 9 OK status={waited.get('status')}")

    print("STEP 10 - ingest_status terminal payload")
    final_status = await _call(s, "ingest_status", {"job_id": job_id})
    if not isinstance(final_status, dict):
        raise TypeError(f"STEP 10 KO ingest_status non-dict: {final_status}")
    lifecycle = final_status.get("status")
    if lifecycle not in {"queued", "running", "awaiting_authentication", "succeeded", "failed"}:
        raise RuntimeError(f"STEP 10 KO invalid lifecycle: {final_status}")
    if lifecycle == "succeeded":
        if int(final_status.get("progress_percent", -1)) != 100:
            raise RuntimeError(f"STEP 10 KO succeeded without progress_percent=100: {final_status}")
        for key in ("pages_scraped", "indexed_chunks"):
            if key not in final_status:
                raise RuntimeError(f"STEP 10 KO missing success field {key}: {final_status}")
    if lifecycle == "failed" and not final_status.get("error_message") and not final_status.get("message"):
        raise RuntimeError(f"STEP 10 KO failed without explicit error payload/message: {final_status}")
    print(f"STEP 10 OK status={lifecycle}")

    print("STEP 11 - persisted artifacts")
    for p in (Path("data/raw/ingest_jobs.json"), Path("data/raw/topic_routes.json"), Path("data/raw/site_sync_state.json")):
        if not p.exists():
            raise RuntimeError(f"STEP 11 KO missing file: {p}")
        text = p.read_text(encoding="utf-8").strip()
        if not text:
            raise RuntimeError(f"STEP 11 KO empty file: {p}")
        json.loads(text)
    print("STEP 11 OK")

    print("STEP 12 - restart reload + interrupted job check")
    import subprocess

    enqueue_code = r'''
import asyncio
from sive.app.mcp_server import build_server


def _extract_text(raw):
    structured = getattr(raw, "structured_content", None)
    if isinstance(structured, dict) and "result" in structured:
        return structured["result"]
    structured_legacy = getattr(raw, "structuredContent", None)
    if isinstance(structured_legacy, dict) and "result" in structured_legacy:
        return structured_legacy["result"]
    content = getattr(raw, "content", None)
    if isinstance(content, list) and content:
        text = getattr(content[0], "text", None)
        if isinstance(text, str):
            return text
    if isinstance(raw, tuple) and len(raw) > 1 and isinstance(raw[1], dict) and "result" in raw[1]:
        return raw[1]["result"]
    if isinstance(raw, dict) and "result" in raw:
        return raw["result"]
    if isinstance(raw, str):
        return raw
    return str(raw)


async def main():
    s = build_server()
    out = await s.call_tool("ingest", {"url": "https://docs.python.org/3/"})
    print(_extract_text(out))
asyncio.run(main())
'''
    proc = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-c", enqueue_code],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"STEP 12 KO unable to enqueue restart-test job: {proc.stderr or proc.stdout}")

    parsed = None
    try:
        parsed = json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        start = proc.stdout.find("{")
        end = proc.stdout.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(proc.stdout[start : end + 1])
            except json.JSONDecodeError:
                parsed = None
    if not isinstance(parsed, dict) or not parsed.get("job_id"):
        raise RuntimeError(f"STEP 12 KO could not parse restart-test job payload: {proc.stdout}")
    interrupted_job_id = str(parsed["job_id"])

    s2 = build_server()
    interrupted = await _call(s2, "ingest_status", {"job_id": interrupted_job_id})
    if not isinstance(interrupted, dict):
        raise TypeError(f"STEP 12 KO interrupted job status non-dict: {interrupted}")
    if interrupted.get("status") != "failed":
        raise RuntimeError(f"STEP 12 KO interrupted job not marked failed after restart: {interrupted}")
    msg = (interrupted.get("error_message") or interrupted.get("error") or interrupted.get("message") or "").lower()
    if "restart" not in msg and "interrupted" not in msg and "shutdown" not in msg:
        raise RuntimeError(f"STEP 12 KO interrupted failure message does not mention restart/interruption: {interrupted}")
    print("STEP 12 OK")

    print("STEP 13 - post-ingestion retrieval")
    visible_after = await _call(s2, "list_indexed_doc_sites", {})
    visible_after_text = visible_after if isinstance(visible_after, str) else json.dumps(visible_after)
    if site_id not in visible_after_text:
        raise RuntimeError("STEP 13 KO ingested site not visible again in list_indexed_doc_sites")

    search_any = await _call(s2, "search_documentation", {"query": "PyMuPDF document"})
    if not isinstance(search_any, str) or "No result found" in search_any:
        raise RuntimeError(f"STEP 13 KO global retrieval missing relevant content: {search_any}")

    routed = await _call(s2, "search_documentation", {"query": "How to open a PDF?", "topic": TARGET_TOPIC})
    if not isinstance(routed, str) or "Topic route applied" not in routed:
        raise RuntimeError(f"STEP 13 KO topic route not applied: {routed}")
    print("STEP 13 OK")

    print("SUCCESS")


def run() -> None:
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"FAILED: {exc}")
        raise


if __name__ == "__main__":
    run()
