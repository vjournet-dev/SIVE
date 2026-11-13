import httpx

from sive.domain.ingest import service as ingest_service


class _RemotePdfClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return httpx.Response(
            200,
            content=b"%PDF-1.4 fake pdf bytes",
            headers={"content-type": "application/pdf"},
            request=httpx.Request("GET", url),
        )


def test_load_pages_for_site_uses_remote_document_loader(monkeypatch):
    captured = {}

    def _fake_load_remote_pages(*args, **kwargs):
        captured.update(kwargs)
        return ["page"]

    monkeypatch.setattr(ingest_service, "load_remote_pages", _fake_load_remote_pages)

    site = ingest_service.SiteDefinition(
        site_id="remote-pdf",
        site_name="manual.pdf",
        start_url="https://example.com/manual.pdf",
        allowed_host="example.com",
        allowed_path_prefix="/",
    )

    pages = ingest_service.load_pages_for_site(
        site,
        max_pages=10,
        delay=0.0,
        crawl_progress_every=0,
        progress_callback=None,
        auth_session={"cookies": {"FedAuth": "x"}, "headers": {}},
    )

    assert pages == ["page"]
    assert captured.get("auth_session") == {"cookies": {"FedAuth": "x"}, "headers": {}}