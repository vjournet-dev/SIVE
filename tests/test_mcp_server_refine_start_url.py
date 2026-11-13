import httpx

from sive.domain.discovery import service as discovery_service


class _FakeResponse:
    def __init__(self, status_code: int, content_type: str = "text/html", text: str = ""):
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "request failed",
                request=httpx.Request("GET", "https://example.invalid"),
                response=httpx.Response(self.status_code),
            )


class _FakeClient:
    def __init__(self, mapping: dict[str, _FakeResponse]):
        self.mapping = mapping

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return self.mapping.get(url, _FakeResponse(status_code=404))


def test_refine_doc_start_url_probes_intro_when_docs_root_fails(monkeypatch):
    mapping = {
        "https://playwright.dev/docs": _FakeResponse(status_code=404),
        "https://playwright.dev/docs/intro": _FakeResponse(status_code=200, content_type="text/html", text="<html></html>"),
    }
    result = discovery_service.refine_doc_start_url(
        "https://playwright.dev/docs",
        http_client_factory=lambda **_: _FakeClient(mapping),
    )

    assert result == "https://playwright.dev/docs/intro"
