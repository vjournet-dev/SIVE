import logging
from typing import ClassVar

import httpx
import pytest

from sive.domain.auth import browser as auth_browser
from sive.domain.auth import session as auth_session
from sive.infra.web import scraper


class _BlockedHttpClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return httpx.Response(
            429,
            headers={"content-type": "text/html; charset=UTF-8"},
            text="<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>Blocked</body></html>",
            request=httpx.Request("GET", url),
        )


def test_requires_browser_fetch_for_challenge_page():
    response = httpx.Response(
        429,
        headers={"content-type": "text/html; charset=UTF-8"},
        text="<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>Blocked</body></html>",
        request=httpx.Request("GET", "https://example.com/docs"),
    )

    assert scraper._requires_browser_fetch(response) is True


def test_playwright_unavailable_is_debug_only(monkeypatch, caplog):
    def _raise_missing_playwright():
        raise RuntimeError("Playwright is unavailable")

    monkeypatch.setattr(scraper, "_get_sync_playwright", _raise_missing_playwright)

    with caplog.at_level(logging.DEBUG, logger=scraper.__name__):
        assert scraper._fetch_html_with_playwright("https://example.com/docs", timeout_seconds=1.0) is None

    matching_records = [record for record in caplog.records if "not installed" in record.message]
    assert len(matching_records) == 1
    assert matching_records[0].levelno == logging.DEBUG


def test_extract_links_preserves_hosteddocs_query_based_file_links():
    html = (
        '<html><body><a href="/sites/engineering/Shared%20Documents/Forms/AllItems.aspx?'
        'id=%2Fsites%2Fengineering%2FShared%20Documents%2FPolicies%2Fguide.pdf">PDF</a></body></html>'
    )

    links = list(scraper.extract_links(html, "https://contoso.hosteddocs.com/sites/engineering/docs"))

    assert links == [
        (
            "https://contoso.hosteddocs.com/sites/engineering/Shared%20Documents/Forms/AllItems.aspx?"
            "id=%2Fsites%2Fengineering%2FShared%20Documents%2FPolicies%2Fguide.pdf"
        )
    ]


def test_extract_links_strips_irrelevant_query_parameters_for_normal_docs_links():
    html = '<html><body><a href="/docs/intro?utm_source=test#section">Intro</a></body></html>'

    links = list(scraper.extract_links(html, "https://example.com/docs/start"))

    assert links == ["https://example.com/docs/intro"]


def test_crawl_docs_uses_browser_fallback_for_blocked_html(monkeypatch):
    monkeypatch.setattr(scraper.httpx, "Client", lambda **_: _BlockedHttpClient())
    monkeypatch.setattr(scraper.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        scraper,
        "_fetch_html_with_playwright",
        lambda url, timeout_seconds: (
            "<html><head><title>Tutorial</title></head><body><main><h1>Intro</h1><p>Hello world</p></main></body></html>",
            url,
        ),
    )

    pages = scraper.crawl_docs(
        start_url="https://pymupdf.readthedocs.io/en/latest/tutorial.html",
        allowed_host="pymupdf.readthedocs.io",
        allowed_path_prefix="/en/",
        site_id="pymupdf-readthedocs-io-en",
        site_name="pymupdf.readthedocs.io",
        max_pages=1,
        request_delay_seconds=0.0,
    )

    assert len(pages) == 1
    assert pages[0].url == "https://pymupdf.readthedocs.io/en/latest/tutorial.html"
    assert pages[0].title == "Tutorial"
    assert "Hello world" in pages[0].content


class _HtmlWithRemotePdfLinkClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=UTF-8"},
            text=(
                "<html><head><title>Docs Home</title></head>"
                "<body><main><h1>Intro</h1><p>Hello world</p>"
                "<a href=\"https://contoso.hosteddocs.com/sites/engineering/Shared%20Documents/guide.pdf\">"
                "PDF guide</a></main></body></html>"
            ),
            request=httpx.Request("GET", url),
        )


class _MultiSeedRedirectClient:
    requested_urls: ClassVar[list[str]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        self.requested_urls.append(url)
        effective_url = url if url.endswith("/guide/") else "https://learn.microsoft.com/en-us/azure/developer/"
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=UTF-8"},
            text=(
                "<html><head><title>Docs</title></head>"
                "<body><main><h1>Documentation</h1><p>Scoped content</p></main></body></html>"
            ),
            request=httpx.Request("GET", effective_url),
        )


def test_crawl_docs_visits_multiple_seeds_and_rejects_redirect_outside_prefixes(monkeypatch):
    _MultiSeedRedirectClient.requested_urls = []
    monkeypatch.setattr(scraper.httpx, "Client", lambda **_: _MultiSeedRedirectClient())
    monkeypatch.setattr(scraper.time, "sleep", lambda _seconds: None)
    guide_url = "https://learn.microsoft.com/en-us/office/open-xml/guide/"
    api_url = "https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml"

    pages = scraper.crawl_docs(
        start_url=guide_url,
        start_urls=[api_url],
        allowed_host="learn.microsoft.com",
        allowed_path_prefix="/en-us/office/open-xml/",
        allowed_path_prefixes=["/en-us/dotnet/api/documentformat.openxml"],
        site_id="openxml",
        site_name="Open XML",
        max_pages=2,
        request_delay_seconds=0.0,
    )

    assert _MultiSeedRedirectClient.requested_urls == [guide_url, api_url]
    assert [page.url for page in pages] == [guide_url]


def test_crawl_docs_loads_supported_remote_document_links(monkeypatch):
    monkeypatch.setattr(scraper.httpx, "Client", lambda **_: _HtmlWithRemotePdfLinkClient())
    monkeypatch.setattr(scraper.time, "sleep", lambda _seconds: None)

    remote_pdf_page = scraper.DocPage(
        site_id="contoso-hosteddocs-engineering",
        site_name="contoso.hosteddocs.com",
        url="https://contoso.hosteddocs.com/sites/engineering/Shared%20Documents/guide.pdf",
        title="guide.pdf",
        content="PDF extracted content",
        content_hash="pdf-hash",
        sections=[scraper.DocSection(heading="Page 1", level=1, content="PDF extracted content")],
    )

    monkeypatch.setattr(scraper, "_load_remote_pages_for_crawl", lambda *args, **kwargs: [remote_pdf_page])

    pages = scraper.crawl_docs(
        start_url="https://contoso.hosteddocs.com/sites/engineering/docs",
        allowed_host="contoso.hosteddocs.com",
        allowed_path_prefix="/sites/engineering/",
        site_id="contoso-hosteddocs-engineering",
        site_name="contoso.hosteddocs.com",
        max_pages=5,
        request_delay_seconds=0.0,
    )

    assert len(pages) == 2
    assert pages[0].title == "Docs Home"
    assert pages[1].title == "guide.pdf"


def test_crawl_docs_raises_explicit_error_when_bot_protection_blocks_all_pages(monkeypatch):
    monkeypatch.setattr(scraper.httpx, "Client", lambda **_: _BlockedHttpClient())
    monkeypatch.setattr(scraper.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(scraper, "_fetch_html_with_playwright", lambda url, timeout_seconds: None)

    with pytest.raises(scraper.AntiBotProtectionError, match="protected by anti-bot"):
        scraper.crawl_docs(
            start_url="https://pymupdf.readthedocs.io/en/latest/tutorial.html",
            allowed_host="pymupdf.readthedocs.io",
            allowed_path_prefix="/en/",
            site_id="pymupdf-readthedocs-io-en",
            site_name="pymupdf.readthedocs.io",
            max_pages=1,
            request_delay_seconds=0.0,
        )


class _AuthRequiredHttpClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return httpx.Response(
            401,
            headers={"content-type": "text/html; charset=UTF-8"},
            text="<html><head><title>Sign in</title></head><body><form><input type=\"password\" /></form></body></html>",
            request=httpx.Request("GET", url),
        )


class _hosteddocsShellHttpClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=UTF-8"},
            text=(
                "<html><head><title>Site</title></head>"
                "<body><script>window._spPageContextInfo = {};</script></body></html>"
            ),
            request=httpx.Request("GET", url),
        )


class _hosteddocsAllItemsFolderClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=UTF-8"},
            text=(
                "<html><head><title>Folder Listing</title></head>"
                "<body><main><h1>00.PILOTAGE</h1><p>Folder content</p></main></body></html>"
            ),
            request=httpx.Request("GET", url),
            extensions={
                "history": [],
            },
        )


class _PublicDocsWithAuthKeywordsClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=UTF-8"},
            text=(
                "<html><head><title>Getting Started Guide</title></head>"
                "<body>"
                "<main><h1>AgentOS Getting Started</h1>"
                "<p>This guide mentions OAuth and SSO options for integrations.</p>"
                "<p>No authentication is required to read this documentation.</p>"
                "</main>"
                "</body></html>"
            ),
            request=httpx.Request("GET", url),
        )


def test_crawl_docs_raises_authentication_required_when_login_page_detected(monkeypatch):
    monkeypatch.setattr(scraper.httpx, "Client", lambda **_: _AuthRequiredHttpClient())
    monkeypatch.setattr(scraper.time, "sleep", lambda _seconds: None)

    with pytest.raises(auth_session.AuthenticationRequiredError, match="Authentication is required") as exc_info:
        scraper.crawl_docs(
            start_url="https://contoso.hosteddocs.com/sites/engineering/docs",
            allowed_host="contoso.hosteddocs.com",
            allowed_path_prefix="/sites/engineering/",
            site_id="contoso-hosteddocs-engineering",
            site_name="contoso.hosteddocs.com",
            max_pages=1,
            request_delay_seconds=0.0,
        )

    assert exc_info.value.login_url == "https://contoso.hosteddocs.com/sites/engineering/docs"


def test_crawl_docs_canonicalizes_hosteddocs_allitems_folder_url(monkeypatch):
    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str):
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=UTF-8"},
                text=(
                    "<html><head><title>Folder Listing</title></head>"
                    "<body><main><h1>00.PILOTAGE</h1><p>Folder content</p></main></body></html>"
                ),
                request=httpx.Request(
                    "GET",
                    httpx.URL(
                "https://talan0.hosteddocs.com/sites/GRP-TAS-ProjetsApplicatifs/Shared%20Documents/Forms/AllItems.aspx"
                "?id=%2Fsites%2FGRP-TAS-ProjetsApplicatifs%2FShared%20Documents%2FGeneral%2F01-Projets%2FRTE%2F03-LITTLE%20BLUE%2F00.PILOTAGE"
                    ),
                ),
                extensions={"history": []},
            )

    monkeypatch.setattr(scraper.httpx, "Client", lambda **_: _Client())
    monkeypatch.setattr(scraper.time, "sleep", lambda _seconds: None)

    pages = scraper.crawl_docs(
        start_url="https://talan0.hosteddocs.com/sites/GRP-TAS-ProjetsApplicatifs/Shared%20Documents/General/01-Projets/RTE/03-LITTLE%20BLUE/00.PILOTAGE/",
        allowed_host="talan0.hosteddocs.com",
        allowed_path_prefix="/sites/GRP-TAS-ProjetsApplicatifs/Shared%20Documents/General/01-Projets/RTE/03-LITTLE%20BLUE/00.PILOTAGE/",
        site_id="talan0-hosteddocs-pilotage",
        site_name="talan0.hosteddocs.com",
        max_pages=1,
        request_delay_seconds=0.0,
    )

    assert len(pages) == 1
    assert pages[0].url == (
        "https://talan0.hosteddocs.com/sites/GRP-TAS-ProjetsApplicatifs/Shared%20Documents/General/"
        "01-Projets/RTE/03-LITTLE%20BLUE/00.PILOTAGE"
    )


def test_crawl_docs_raises_authentication_required_for_protected_shell_without_login_url(monkeypatch):
    monkeypatch.setattr(scraper.httpx, "Client", lambda **_: _hosteddocsShellHttpClient())
    monkeypatch.setattr(scraper.time, "sleep", lambda _seconds: None)

    with pytest.raises(auth_session.AuthenticationRequiredError, match="authenticate_ingest_job") as exc_info:
        scraper.crawl_docs(
            start_url="https://contoso.hosteddocs.com/sites/engineering/docs",
            allowed_host="contoso.hosteddocs.com",
            allowed_path_prefix="/sites/engineering/",
            site_id="contoso-hosteddocs-engineering",
            site_name="contoso.hosteddocs.com",
            max_pages=1,
            request_delay_seconds=0.0,
        )

    assert exc_info.value.login_url == "https://contoso.hosteddocs.com/sites/engineering/docs"


def test_crawl_docs_does_not_flag_public_docs_that_mention_oauth_or_sso(monkeypatch):
    monkeypatch.setattr(scraper.httpx, "Client", lambda **_: _PublicDocsWithAuthKeywordsClient())
    monkeypatch.setattr(scraper.time, "sleep", lambda _seconds: None)

    pages = scraper.crawl_docs(
        start_url="https://docs.agentos.sh/getting-started",
        allowed_host="docs.agentos.sh",
        allowed_path_prefix="/",
        site_id="docs-agentos",
        site_name="docs.agentos.sh",
        max_pages=1,
        request_delay_seconds=0.0,
    )

    assert len(pages) == 1
    assert pages[0].title == "Getting Started Guide"
    assert "OAuth" in pages[0].content


def test_crawl_docs_does_not_flag_public_oauth_authitecture_page_path(monkeypatch):
    monkeypatch.setattr(scraper.httpx, "Client", lambda **_: _PublicDocsWithAuthKeywordsClient())
    monkeypatch.setattr(scraper.time, "sleep", lambda _seconds: None)

    pages = scraper.crawl_docs(
        start_url="https://docs.agentos.sh/architecture/oauth-auth",
        allowed_host="docs.agentos.sh",
        allowed_path_prefix="/",
        site_id="docs-agentos",
        site_name="docs.agentos.sh",
        max_pages=1,
        request_delay_seconds=0.0,
    )

    assert len(pages) == 1
    assert "OAuth" in pages[0].content


def test_extract_allowed_host_cookies_includes_subdomains():
    cookies = [
        {"domain": ".contoso.hosteddocs.com", "name": "FedAuth", "value": "token"},
        {"domain": "login.microsoftonline.com", "name": "ESTSAUTH", "value": "ignored"},
    ]

    extracted = auth_session._extract_allowed_host_cookies(cookies, "contoso.hosteddocs.com")

    assert extracted == {"FedAuth": "token"}


def test_extract_allowed_host_cookies_includes_parent_domain_for_m365_flows():
    cookies = [
        {"domain": ".hosteddocs.com", "name": "rtFa", "value": "tenant-scope-token"},
    ]

    extracted = auth_session._extract_allowed_host_cookies(cookies, "contoso.hosteddocs.com")

    assert extracted == {"rtFa": "tenant-scope-token"}


def test_extract_allowed_host_cookies_keeps_last_value_for_duplicate_cookie_name():
    cookies = [
        {"domain": ".contoso.hosteddocs.com", "name": "FedAuth", "value": "old"},
        {"domain": "contoso.hosteddocs.com", "name": "FedAuth", "value": "new"},
    ]

    extracted = auth_session._extract_allowed_host_cookies(cookies, "contoso.hosteddocs.com")

    assert extracted == {"FedAuth": "new"}


def test_has_strong_auth_cookie_detects_auth_session_markers():
    assert auth_session._has_strong_auth_cookie({"FedAuth": "x"}) is True
    assert auth_session._has_strong_auth_cookie({"session_token": "x"}) is True
    assert auth_session._has_strong_auth_cookie({"Other": "x"}) is False


def test_crawl_docs_prefers_browser_session_path_when_auth_session_is_provided(monkeypatch):
    monkeypatch.setattr(scraper.time, "sleep", lambda _seconds: None)

    browser_page = scraper.DocPage(
        site_id="contoso-hosteddocs-engineering",
        site_name="contoso.hosteddocs.com",
        url="https://contoso.hosteddocs.com/sites/engineering/docs/page1",
        title="Page 1",
        content="Hello from authenticated browser crawl",
        content_hash="hash",
        sections=[],
    )

    monkeypatch.setattr(
        scraper,
        "_crawl_docs_with_playwright_session",
        lambda **kwargs: [browser_page],
    )

    pages = scraper.crawl_docs(
        start_url="https://contoso.hosteddocs.com/sites/engineering/docs",
        allowed_host="contoso.hosteddocs.com",
        allowed_path_prefix="/sites/engineering/",
        site_id="contoso-hosteddocs-engineering",
        site_name="contoso.hosteddocs.com",
        max_pages=1,
        request_delay_seconds=0.0,
        auth_session={"cookies": {"sessionid": "abc"}, "headers": {}, "storage_state": {"cookies": []}},
    )

    assert len(pages) == 1
    assert pages[0].title == "Page 1"


def test_extract_storage_state_returns_context_payload():
    class _FakeContext:
        def storage_state(self):
            return {"cookies": [{"name": "FedAuth", "value": "x"}], "origins": []}

    assert auth_session._extract_storage_state(_FakeContext()) == {
        "cookies": [{"name": "FedAuth", "value": "x"}],
        "origins": [],
    }


def test_crawl_docs_with_playwright_session_reuses_storage_state(monkeypatch):
    created_context_kwargs = {}
    injected_cookies = []

    class _FakePage:
        url = "https://contoso.hosteddocs.com/sites/engineering/docs/page1"

        def goto(self, url, wait_until, timeout):
            self.url = url

        def wait_for_load_state(self, state, timeout):
            return None

        def content(self):
            return "<html><head><title>Page 1</title></head><body><main><h1>Intro</h1><p>Hello</p></main></body></html>"

        def close(self):
            return None

    class _FakeContext:
        def set_extra_http_headers(self, headers):
            self.headers = headers

        def new_page(self):
            return _FakePage()

        def close(self):
            return None

    class _FakeBrowser:
        def new_context(self, **kwargs):
            created_context_kwargs.update(kwargs)
            return _FakeContext()

        def close(self):
            return None

    class _FakePlaywright:
        class chromium:
            @staticmethod
            def launch(headless):
                return _FakeBrowser()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    pages = auth_browser.crawl_docs_with_playwright_session(
        start_url="https://contoso.hosteddocs.com/sites/engineering/docs",
        allowed_host="contoso.hosteddocs.com",
        allowed_path_prefix="/sites/engineering/",
        site_id="contoso-hosteddocs-engineering",
        site_name="contoso.hosteddocs.com",
        max_pages=1,
        timeout_seconds=5,
        progress_callback=None,
        auth_session={
            "cookies": {"FedAuth": "token"},
            "headers": {"Authorization": "Bearer x"},
            "storage_state": {
                "cookies": [{"name": "FedAuth", "value": "token", "domain": "contoso.hosteddocs.com", "path": "/"}],
                "origins": [],
            },
        },
        normalize_url=scraper.normalize_url,
        is_allowed_url=scraper.is_allowed_url,
        extract_page_content=scraper.extract_page_content,
        extract_links=scraper.extract_links,
        get_sync_playwright=lambda: (lambda: _FakePlaywright()),
        inject_cookies_into_context=lambda *args: injected_cookies.append(True),
    )

    assert len(pages) == 1
    assert created_context_kwargs["storage_state"]["cookies"][0]["name"] == "FedAuth"
    assert injected_cookies == []


def test_build_auth_session_from_config_supports_oauth():
    session = auth_session._build_auth_session_from_config(
        {
            "type": "oauth",
            "token": "abc.def.ghi",
            "token_type": "Bearer",
        },
        "contoso.hosteddocs.com",
    )

    headers = session.get("headers", {})
    assert headers["Authorization"] == "Bearer abc.def.ghi"


def test_build_auth_session_from_config_supports_basic_auth():
    session = auth_session._build_auth_session_from_config(
        {
            "type": "basic",
            "username": "alice",
            "password": "secret",
        },
        "example.com",
    )

    headers = session.get("headers", {})
    assert headers["Authorization"].startswith("Basic ")


def test_build_auth_session_from_config_supports_cookie_payload_as_json_string():
    session = auth_session._build_auth_session_from_config(
        {
            "type": "cookie",
            "cookies": "[{\"domain\": \".hosteddocs.com\", \"name\": \"FedAuth\", \"value\": \"token\"}]",
        },
        "contoso.hosteddocs.com",
    )

    assert session.get("cookies", {}) == {"FedAuth": "token"}


def test_build_playwright_cookie_entries_uses_url_shape_without_path():
    entries = auth_session._build_playwright_cookie_entries(
        {"FedAuth": "token"},
        "contoso.hosteddocs.com",
    )

    assert entries == [
        {
            "name": "FedAuth",
            "value": "token",
            "url": "https://contoso.hosteddocs.com",
        }
    ]


def test_inject_cookies_into_context_falls_back_to_domain_path_when_url_shape_fails():
    class _FakeContext:
        def __init__(self):
            self.calls = []

        def add_cookies(self, payload):
            self.calls.append(payload)
            if len(self.calls) == 1:
                raise RuntimeError("url mode rejected")

    fake_context = _FakeContext()

    auth_session._inject_cookies_into_context(
        fake_context,
        {"FedAuth": "token"},
        "contoso.hosteddocs.com",
    )

    assert len(fake_context.calls) == 2
    assert fake_context.calls[0][0]["url"] == "https://contoso.hosteddocs.com"
    assert fake_context.calls[1][0]["domain"] == "contoso.hosteddocs.com"
    assert fake_context.calls[1][0]["path"] == "/"

