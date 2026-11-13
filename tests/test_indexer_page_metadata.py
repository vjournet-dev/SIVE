from sive.domain.index import indexing as indexer
from sive.domain.index.indexing import index_pages_incrementally, make_chunks
from sive.infra.web.scraper import DocPage, DocSection, hash_content


def test_make_chunks_propagates_pdf_page_number_metadata():
    content = "Page 1\nIntro content\n\nPage 2\nAdvanced content"
    page = DocPage(
        site_id="pdf-doc",
        site_name="PDF Doc",
        url="file:///manual.pdf",
        title="manual.pdf",
        content=content,
        content_hash=hash_content(content),
        sections=[
            DocSection(heading="Page 1", level=1, content="Intro content"),
            DocSection(heading="Page 2", level=1, content="Advanced content"),
        ],
    )

    chunks = make_chunks([page], chunk_size=500, overlap=50)

    assert len(chunks) == 2
    assert chunks[0].page_number == 1
    assert chunks[0].section_heading == "Page 1"
    assert chunks[0].source_kind == "pdf"
    assert chunks[0].section_index == 0
    assert chunks[0].section_count == 2
    assert chunks[1].page_number == 2
    assert chunks[1].section_heading == "Page 2"
    assert chunks[1].source_kind == "pdf"
    assert chunks[1].section_index == 1
    assert chunks[1].section_count == 2


def test_make_chunks_sets_markdown_source_kind_for_md_urls():
    content = "# Intro\n\nHello"
    page = DocPage(
        site_id="md-doc",
        site_name="Markdown Doc",
        url="https://example.com/guide.md",
        title="guide.md",
        content=content,
        content_hash=hash_content(content),
        sections=[DocSection(heading="Intro", level=1, content="Hello")],
    )

    chunks = make_chunks([page], chunk_size=500, overlap=50)

    assert len(chunks) == 1
    assert chunks[0].source_kind == "markdown"


def test_make_chunks_adds_markdown_chunk_signals():
    content = "Intro\n\n[code:python]\nprint('hi')\n[/code]\n\nSee https://example.com/ref"
    page = DocPage(
        site_id="md-doc",
        site_name="Markdown Doc",
        url="https://example.com/guide.md",
        title="guide.md",
        content=content,
        content_hash=hash_content(content),
        sections=[DocSection(heading="Intro", level=2, content=content)],
    )

    chunks = make_chunks([page], chunk_size=500, overlap=50)

    assert len(chunks) == 1
    assert chunks[0].source_kind == "markdown"
    assert chunks[0].section_level == 2
    assert chunks[0].has_code_block is True
    assert chunks[0].has_link_target is True


class _FakeCollection:
    def __init__(self):
        self.upsert_calls = []
        self.delete_calls = []

    def upsert(self, ids, documents, metadatas):
        self.upsert_calls.append(
            {
                "ids": ids,
                "documents": documents,
                "metadatas": metadatas,
            }
        )

    def delete(self, where):
        self.delete_calls.append(where)


def test_upsert_chunks_dedupes_duplicate_chunk_ids():
    page = DocPage(
        site_id="dup-site",
        site_name="Dup Site",
        url="https://example.com/docs/page",
        title="Page",
        content="Hello world",
        content_hash=hash_content("Hello world"),
        sections=[DocSection(heading="Intro", level=1, content="Hello world")],
    )
    chunks = make_chunks([page], chunk_size=500, overlap=50)
    duplicated = chunks + [chunks[0]]

    fake = _FakeCollection()
    indexed_count = indexer._upsert_chunks(fake, duplicated, batch_size=128)

    assert indexed_count == len(chunks)
    all_ids = [chunk_id for call in fake.upsert_calls for chunk_id in call["ids"]]
    assert len(all_ids) == len(set(all_ids))


def test_index_pages_incrementally_dedupes_pages_with_same_url(tmp_path, monkeypatch):
    fake = _FakeCollection()
    monkeypatch.setattr(indexer, "_get_collection", lambda *args, **kwargs: fake)

    url = "https://example.com/docs/page"
    page1 = DocPage(
        site_id="dup-site",
        site_name="Dup Site",
        url=url,
        title="Page",
        content="Hello world",
        content_hash=hash_content("Hello world"),
        sections=[DocSection(heading="Intro", level=1, content="Hello world")],
    )
    page2 = DocPage(
        site_id="dup-site",
        site_name="Dup Site",
        url=url,
        title="Page",
        content="Hello world",
        content_hash=hash_content("Hello world"),
        sections=[DocSection(heading="Intro", level=1, content="Hello world")],
    )

    result = index_pages_incrementally(
        pages=[page1, page2],
        chroma_dir=tmp_path,
        collection_name="docs",
        state_path=tmp_path / "state.json",
        reset_collection=True,
        batch_size=128,
        chunk_size=500,
        overlap=50,
    )

    assert result.changed_pages == 1
    all_ids = [chunk_id for call in fake.upsert_calls for chunk_id in call["ids"]]
    assert len(all_ids) == len(set(all_ids))