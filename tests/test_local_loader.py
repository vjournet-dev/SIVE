import json

import httpx
import pytest

from sive.domain.auth.session import AuthenticationRequiredError
from sive.domain.parse.loader import is_supported_remote_source_url, load_local_pages, load_remote_pages
from sive.infra.web.scraper import DocSection


def test_load_local_pages_supports_html_and_json_files(tmp_path):
    html_path = tmp_path / "guide.html"
    json_path = tmp_path / "config.json"

    html_path.write_text(
        "<html><head><title>Guide</title></head><body><main><h1>Intro</h1><p>Hello HTML</p></main></body></html>",
        encoding="utf-8",
    )
    json_path.write_text(json.dumps({"name": "demo", "items": [1, 2, 3]}), encoding="utf-8")

    pages = load_local_pages(tmp_path, site_id="local-docs", site_name="Local Docs")

    assert len(pages) == 2
    titles = {page.title for page in pages}
    assert "Guide" in titles
    assert "config.json" in titles
    urls = {page.url for page in pages}
    assert html_path.resolve().as_uri() in urls
    assert json_path.resolve().as_uri() in urls

    json_page = next(page for page in pages if page.title == "config.json")
    assert json_page.sections == [
        DocSection(heading="name", level=1, content="demo"),
        DocSection(heading="items", level=1, content="[0]: 1\n[1]: 2\n[2]: 3"),
    ]


def test_load_local_pages_supports_csv_file(tmp_path):
    csv_path = tmp_path / "users.csv"
    csv_path.write_text("name,role\nAlice,admin\nBob,viewer\n", encoding="utf-8")

    pages = load_local_pages(csv_path, site_id="csv-doc", site_name="CSV Doc")

    assert len(pages) == 1
    assert pages[0].title == "users.csv"
    assert pages[0].sections == [
        DocSection(
            heading="users.csv / Summary",
            level=1,
            content="row_count: 2\ncolumn_count: 2\nname.non_empty_count: 2\nrole.non_empty_count: 2",
        ),
        DocSection(heading="users.csv / Columns", level=1, content="columns: name, role\nrow_count: 2"),
        DocSection(heading="Row 1 - name=Alice | role=admin", level=1, content="name: Alice\nrole: admin"),
        DocSection(heading="Row 2 - name=Bob | role=viewer", level=1, content="name: Bob\nrole: viewer"),
    ]


def test_load_local_pages_supports_single_html_file(tmp_path):
    html_path = tmp_path / "tutorial.html"
    html_path.write_text(
        "<html><head><title>Tutorial</title></head><body><main><p>Local HTML doc</p></main></body></html>",
        encoding="utf-8",
    )

    pages = load_local_pages(html_path, site_id="local-doc", site_name="Local Doc")

    assert len(pages) == 1
    assert pages[0].title == "Tutorial"
    assert "Local HTML doc" in pages[0].content


def test_load_local_pages_supports_markdown_file(tmp_path):
    markdown_path = tmp_path / "guide.md"
    markdown_path.write_text(
        "# Getting Started\n\nInstall the package first.\n\n## Configuration\n\n- Set API_URL\n- Set TOKEN\n",
        encoding="utf-8",
    )

    pages = load_local_pages(markdown_path, site_id="md-doc", site_name="Markdown Doc")

    assert len(pages) == 1
    assert pages[0].title == "guide.md"
    assert pages[0].sections == [
        DocSection(heading="Getting Started", level=1, content="Install the package first."),
        DocSection(heading="Configuration", level=2, content="Set API_URL\nSet TOKEN"),
    ]


def test_load_local_pages_markdown_ignores_front_matter_and_keeps_links_and_code(tmp_path):
    markdown_path = tmp_path / "advanced.md"
    markdown_path.write_text(
        "---\n"
        "title: Advanced Guide\n"
        "tags:\n"
        "  - docs\n"
        "---\n\n"
        "Overview\n"
        "--------\n\n"
        "Use [API reference](https://example.com/api) and MY_CONFIG_KEY.\n\n"
        "```python\n"
        "def build_url(base_url):\n"
        "    return f\"{base_url}/v1\"\n"
        "```\n",
        encoding="utf-8",
    )

    pages = load_local_pages(markdown_path, site_id="md-advanced", site_name="Markdown Advanced")

    assert len(pages) == 1
    assert pages[0].sections == [
        DocSection(
            heading="Overview",
            level=2,
            content=(
                "Use API reference (https://example.com/api) and MY_CONFIG_KEY.\n\n"
                "[code:python]\n"
                "def build_url(base_url):\n"
                "    return f\"{base_url}/v1\"\n"
                "[/code]"
            ),
        )
    ]


class _FakePdfPage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self):
        return self._text


class _FakePdfReader:
    def __init__(self, *_args, **_kwargs):
        self.pages = [_FakePdfPage("Intro content"), _FakePdfPage("Advanced content")]


class _FakeDocxStyle:
    def __init__(self, name: str):
        self.name = name


class _FakeDocxParagraph:
    def __init__(self, text: str, style_name: str = "Normal"):
        self.text = text
        self.style = _FakeDocxStyle(style_name)


class _FakeDocxDocument:
    def __init__(self, *_args, **_kwargs):
        self.paragraphs = [
            _FakeDocxParagraph("Getting Started", "Heading 1"),
            _FakeDocxParagraph("Install the package first."),
            _FakeDocxParagraph("Configuration", "Heading 2"),
            _FakeDocxParagraph("Set the environment variable."),
        ]


class _FakeWorksheet:
    def __init__(self, title: str, rows: list[tuple[object, ...]]):
        self.title = title
        self._rows = rows

    def iter_rows(self, values_only: bool = False):
        assert values_only is True
        return iter(self._rows)


class _FakeWorkbook:
    def __init__(self, *_args, **_kwargs):
        self.worksheets = [
            _FakeWorksheet("Users", [("name", "role"), ("Alice", "admin"), ("Bob", "viewer")]),
            _FakeWorksheet("Settings", [("key", "value"), ("timeout", 30)]),
        ]

    def close(self):
        return None


def test_load_local_pages_preserves_pdf_pages_as_sections(tmp_path, monkeypatch):
    pdf_path = tmp_path / "manual.pdf"
    pdf_path.write_bytes(b"fake-pdf")
    monkeypatch.setattr("pypdf.PdfReader", _FakePdfReader)

    pages = load_local_pages(pdf_path, site_id="pdf-doc", site_name="PDF Doc")

    assert len(pages) == 1
    assert pages[0].title == "manual.pdf"
    assert [section.heading for section in pages[0].sections] == ["Page 1", "Page 2"]
    assert [section.content for section in pages[0].sections] == ["Intro content", "Advanced content"]
    assert "Page 1\nIntro content" in pages[0].content
    assert "Page 2\nAdvanced content" in pages[0].content


def test_load_local_pages_preserves_docx_headings_as_sections(tmp_path, monkeypatch):
    docx_path = tmp_path / "guide.docx"
    docx_path.write_bytes(b"fake-docx")
    monkeypatch.setattr("docx.Document", _FakeDocxDocument)

    pages = load_local_pages(docx_path, site_id="docx-doc", site_name="DOCX Doc")

    assert len(pages) == 1
    assert pages[0].sections == [
        DocSection(heading="Getting Started", level=1, content="Install the package first."),
        DocSection(heading="Configuration", level=2, content="Set the environment variable."),
    ]


def test_load_local_pages_preserves_xlsx_rows_as_sections(tmp_path, monkeypatch):
    xlsx_path = tmp_path / "report.xlsx"
    xlsx_path.write_bytes(b"fake-xlsx")
    monkeypatch.setattr("openpyxl.load_workbook", lambda **kwargs: _FakeWorkbook())

    pages = load_local_pages(xlsx_path, site_id="xlsx-doc", site_name="XLSX Doc")

    assert len(pages) == 1
    assert pages[0].title == "report.xlsx"
    assert pages[0].sections == [
        DocSection(
            heading="Users / Summary",
            level=1,
            content="row_count: 2\ncolumn_count: 2\nname.non_empty_count: 2\nrole.non_empty_count: 2",
        ),
        DocSection(heading="Users / Columns", level=1, content="columns: name, role\nrow_count: 2"),
        DocSection(heading="Users / Row 1 - name=Alice | role=admin", level=1, content="name: Alice\nrole: admin"),
        DocSection(heading="Users / Row 2 - name=Bob | role=viewer", level=1, content="name: Bob\nrole: viewer"),
        DocSection(
            heading="Settings / Summary",
            level=1,
            content="row_count: 1\ncolumn_count: 2\nkey.non_empty_count: 1\nvalue.non_empty_count: 1",
        ),
        DocSection(heading="Settings / Columns", level=1, content="columns: key, value\nrow_count: 1"),
        DocSection(heading="Settings / Row 1 - key=timeout | value=30", level=1, content="key: timeout\nvalue: 30"),
    ]


class _RemoteJsonClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"project": "demo", "enabled": True},
            request=httpx.Request("GET", url),
        )


class _RemotePdfRedirectClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return httpx.Response(
            200,
            content=b"pdf bytes",
            headers={
                "content-type": "application/pdf",
                "content-disposition": 'inline; filename="pymupdf-readthedocs-io-en-latest.pdf"',
            },
            request=httpx.Request("GET", url),
        )


class _RemoteCsvClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return httpx.Response(
            200,
            text="name,role\nAlice,admin\nBob,viewer\n",
            headers={"content-type": "text/csv; charset=utf-8"},
            request=httpx.Request("GET", url),
        )


class _RemoteXlsxClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return httpx.Response(
            200,
            content=b"xlsx-bytes",
            headers={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            request=httpx.Request("GET", url),
        )


class _RemoteMarkdownClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return httpx.Response(
            200,
            text="# Title\n\nA **short** intro.\n\n## Details\n\n1. Step one\n2. Step two\n",
            headers={"content-type": "text/markdown; charset=utf-8"},
            request=httpx.Request("GET", url),
        )


def test_load_remote_pages_supports_json_url(monkeypatch):
    monkeypatch.setattr("sive.domain.parse.loader.httpx.Client", lambda **_: _RemoteJsonClient())

    pages = load_remote_pages("https://example.com/config.json", site_id="remote-docs", site_name="Remote Docs")

    assert len(pages) == 1
    assert pages[0].title == "config.json"
    assert "demo" in pages[0].content
    assert pages[0].url == "https://example.com/config.json"
    assert pages[0].sections == [
        DocSection(heading="project", level=1, content="demo"),
        DocSection(heading="enabled", level=1, content="true"),
    ]


def test_load_remote_pages_supports_csv_url(monkeypatch):
    monkeypatch.setattr("sive.domain.parse.loader.httpx.Client", lambda **_: _RemoteCsvClient())

    pages = load_remote_pages("https://example.com/users.csv", site_id="remote-csv", site_name="Remote CSV")

    assert len(pages) == 1
    assert pages[0].title == "users.csv"
    assert pages[0].sections == [
        DocSection(
            heading="users.csv / Summary",
            level=1,
            content="row_count: 2\ncolumn_count: 2\nname.non_empty_count: 2\nrole.non_empty_count: 2",
        ),
        DocSection(heading="users.csv / Columns", level=1, content="columns: name, role\nrow_count: 2"),
        DocSection(heading="Row 1 - name=Alice | role=admin", level=1, content="name: Alice\nrole: admin"),
        DocSection(heading="Row 2 - name=Bob | role=viewer", level=1, content="name: Bob\nrole: viewer"),
    ]


def test_load_remote_pages_supports_markdown_url(monkeypatch):
    monkeypatch.setattr("sive.domain.parse.loader.httpx.Client", lambda **_: _RemoteMarkdownClient())

    pages = load_remote_pages("https://example.com/guide.md", site_id="remote-md", site_name="Remote Markdown")

    assert len(pages) == 1
    assert pages[0].title == "guide.md"
    assert pages[0].sections == [
        DocSection(heading="Title", level=1, content="A short intro."),
        DocSection(heading="Details", level=2, content="Step one\nStep two"),
    ]


def test_load_remote_pages_detects_pdf_from_headers_when_redirected_url_has_no_suffix(monkeypatch):
    monkeypatch.setattr("sive.domain.parse.loader.httpx.Client", lambda **_: _RemotePdfRedirectClient())
    monkeypatch.setattr("sive.domain.parse.loader._load_remote_pdf", lambda response, **kwargs: "pdf-page")

    pages = load_remote_pages(
        "https://buildmedia.readthedocs.org/media/pdf/pymupdf/latest/pymupdf.pdf",
        site_id="pymupdf-pdf",
        site_name="PyMuPDF PDF",
    )

    assert pages == ["pdf-page"]


def test_load_remote_pages_preserves_pdf_pages_as_sections(monkeypatch):
    monkeypatch.setattr("sive.domain.parse.loader.httpx.Client", lambda **_: _RemotePdfRedirectClient())
    monkeypatch.setattr("pypdf.PdfReader", _FakePdfReader)

    pages = load_remote_pages(
        "https://example.com/guide.pdf",
        site_id="remote-pdf",
        site_name="Remote PDF",
    )

    assert len(pages) == 1
    assert pages[0].sections == [
        DocSection(heading="Page 1", level=1, content="Intro content"),
        DocSection(heading="Page 2", level=1, content="Advanced content"),
    ]


def test_load_remote_pages_preserves_docx_headings_as_sections(monkeypatch):
    class _RemoteDocxClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str):
            return httpx.Response(
                200,
                content=b"docx-bytes",
                headers={
                    "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                },
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr("sive.domain.parse.loader.httpx.Client", lambda **_: _RemoteDocxClient())
    monkeypatch.setattr("docx.Document", _FakeDocxDocument)

    pages = load_remote_pages("https://example.com/guide.docx", site_id="remote-docx", site_name="Remote DOCX")

    assert len(pages) == 1
    assert pages[0].sections == [
        DocSection(heading="Getting Started", level=1, content="Install the package first."),
        DocSection(heading="Configuration", level=2, content="Set the environment variable."),
    ]


def test_load_remote_pages_preserves_xlsx_rows_as_sections(monkeypatch):
    monkeypatch.setattr("sive.domain.parse.loader.httpx.Client", lambda **_: _RemoteXlsxClient())
    monkeypatch.setattr("openpyxl.load_workbook", lambda **kwargs: _FakeWorkbook())

    pages = load_remote_pages("https://example.com/report.xlsx", site_id="remote-xlsx", site_name="Remote XLSX")

    assert len(pages) == 1
    assert pages[0].title == "report.xlsx"
    assert pages[0].sections == [
        DocSection(
            heading="Users / Summary",
            level=1,
            content="row_count: 2\ncolumn_count: 2\nname.non_empty_count: 2\nrole.non_empty_count: 2",
        ),
        DocSection(heading="Users / Columns", level=1, content="columns: name, role\nrow_count: 2"),
        DocSection(heading="Users / Row 1 - name=Alice | role=admin", level=1, content="name: Alice\nrole: admin"),
        DocSection(heading="Users / Row 2 - name=Bob | role=viewer", level=1, content="name: Bob\nrole: viewer"),
        DocSection(
            heading="Settings / Summary",
            level=1,
            content="row_count: 1\ncolumn_count: 2\nkey.non_empty_count: 1\nvalue.non_empty_count: 1",
        ),
        DocSection(heading="Settings / Columns", level=1, content="columns: key, value\nrow_count: 1"),
        DocSection(heading="Settings / Row 1 - key=timeout | value=30", level=1, content="key: timeout\nvalue: 30"),
    ]


class _RemoteForbiddenClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return httpx.Response(
            403,
            headers={"content-type": "application/pdf"},
            request=httpx.Request("GET", url),
        )


def test_load_remote_pages_raises_authentication_required_on_403(monkeypatch):
    monkeypatch.setattr("sive.domain.parse.loader.httpx.Client", lambda **_: _RemoteForbiddenClient())

    with pytest.raises(AuthenticationRequiredError, match="Authentication is required"):
        load_remote_pages(
            "https://talan0.hosteddocs.com/sites/Talan_Ouest/doc.pdf",
            site_id="remote-pdf",
            site_name="Remote PDF",
        )


def test_load_remote_pages_raises_authenticated_access_error_on_403_with_session(monkeypatch):
    monkeypatch.setattr("sive.domain.parse.loader.httpx.Client", lambda **_: _RemoteForbiddenClient())

    with pytest.raises(AuthenticationRequiredError, match="Authenticated session could not access"):
        load_remote_pages(
            "https://talan0.hosteddocs.com/sites/Talan_Ouest/doc.pdf",
            site_id="remote-pdf",
            site_name="Remote PDF",
            auth_session={"cookies": {"FedAuth": "x"}, "headers": {}},
        )


def test_is_supported_remote_source_url_supports_hosteddocs_query_file_url():
    assert is_supported_remote_source_url(
        "https://contoso.hosteddocs.com/sites/engineering/Shared%20Documents/Forms/AllItems.aspx"
        "?id=%2Fsites%2Fengineering%2FShared%20Documents%2FPolicies%2Fguide.pdf"
    ) is True


class _hosteddocsQueryPdfClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return httpx.Response(
            200,
            content=b"pdf-bytes",
            headers={"content-type": "application/pdf"},
            request=httpx.Request("GET", url),
        )


def test_load_remote_pages_supports_hosteddocs_query_file_url(monkeypatch):
    monkeypatch.setattr("sive.domain.parse.loader.httpx.Client", lambda **_: _hosteddocsQueryPdfClient())
    monkeypatch.setattr("pypdf.PdfReader", _FakePdfReader)

    pages = load_remote_pages(
        "https://contoso.hosteddocs.com/sites/engineering/Shared%20Documents/Forms/AllItems.aspx"
        "?id=%2Fsites%2Fengineering%2FShared%20Documents%2FPolicies%2Fguide.pdf",
        site_id="contoso-hosteddocs-engineering",
        site_name="contoso.hosteddocs.com",
    )

    assert len(pages) == 1
    assert pages[0].title == "guide.pdf"
    assert pages[0].sections == [
        DocSection(heading="Page 1", level=1, content="Intro content"),
        DocSection(heading="Page 2", level=1, content="Advanced content"),
    ]

