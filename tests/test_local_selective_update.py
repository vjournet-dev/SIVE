from sive.domain.ingest.service import update_existing_local_site as update_existing_local_documents
from sive.infra.web.scraper import DocPage, DocSection, hash_content


class _FakeCollection:
    def __init__(self, metadatas: list[dict[str, object]]):
        self._metadatas = metadatas
        self.delete_calls: list[dict[str, str]] = []
        self.upsert_calls: list[dict[str, object]] = []

    def get(self, include):
        assert include == ["metadatas"]
        return {"metadatas": list(self._metadatas)}

    def delete(self, where):
        self.delete_calls.append(where)

    def upsert(self, ids, documents, metadatas):
        self.upsert_calls.append(
            {
                "ids": ids,
                "documents": documents,
                "metadatas": metadatas,
            }
        )


def test_update_existing_local_documents_returns_no_match_when_none_indexed(tmp_path):
    source_dir = tmp_path / "incoming"
    source_dir.mkdir()
    source_file = source_dir / "guide.md"
    source_file.write_text("# Guide\nUpdated", encoding="utf-8")

    page = DocPage(
        site_id="candidate",
        site_name="candidate",
        url=source_file.resolve().as_uri(),
        title="guide.md",
        content="Guide\nUpdated",
        content_hash=hash_content("Guide\nUpdated"),
        sections=[DocSection(heading="guide", level=1, content="Updated")],
    )

    fake_collection = _FakeCollection(metadatas=[])

    payload = update_existing_local_documents(
        str(source_file),
        collection=fake_collection,
        load_local_pages_func=lambda *_args, **_kwargs: [page],
        site_index_state_path_func=lambda site_id: tmp_path / f"{site_id}.state.json",
    )

    assert payload["status"] == "no_match"
    assert payload["updated"] == 0
    assert payload["progress_percent"] == 100
    assert payload["progress_bar"].endswith("100%")
    assert fake_collection.delete_calls == []
    assert fake_collection.upsert_calls == []


def test_update_existing_local_documents_updates_only_existing_directory_matches(tmp_path):
    source_dir = tmp_path / "incoming"
    docs_dir = source_dir / "docs"
    docs_dir.mkdir(parents=True)

    file_a = docs_dir / "a.md"
    file_b = docs_dir / "b.md"
    file_a.write_text("A updated", encoding="utf-8")
    file_b.write_text("B updated", encoding="utf-8")

    page_a = DocPage(
        site_id="candidate",
        site_name="candidate",
        url=file_a.resolve().as_uri(),
        title="a.md",
        content="A updated",
        content_hash=hash_content("A updated"),
        sections=[DocSection(heading="A", level=1, content="A updated")],
    )
    page_b = DocPage(
        site_id="candidate",
        site_name="candidate",
        url=file_b.resolve().as_uri(),
        title="b.md",
        content="B updated",
        content_hash=hash_content("B updated"),
        sections=[DocSection(heading="B", level=1, content="B updated")],
    )

    existing_a_url = (tmp_path / "existing" / "docs" / "a.md").resolve().as_uri()
    existing_remote_url = "https://example.com/docs/a"
    fake_collection = _FakeCollection(
        metadatas=[
            {
                "source_url": existing_a_url,
                "site_id": "local-docs",
                "site_name": "Local Docs",
                "content_hash": "old-hash-a",
            },
            {
                "source_url": existing_remote_url,
                "site_id": "remote-docs",
                "site_name": "Remote Docs",
            },
        ]
    )

    state_path = tmp_path / "local-docs.state.json"
    state_path.write_text("{}", encoding="utf-8")

    payload = update_existing_local_documents(
        str(source_dir),
        collection=fake_collection,
        load_local_pages_func=lambda *_args, **_kwargs: [page_a, page_b],
        site_index_state_path_func=lambda site_id: tmp_path / f"{site_id}.state.json",
    )

    assert payload["status"] == "ok"
    assert payload["checked"] == 2
    assert payload["matched"] == 1
    assert payload["updated"] == 1
    assert payload["skipped"] == 1
    assert payload["changed_pages"] == 1
    assert payload["unchanged_pages"] == 0
    assert payload["progress_percent"] == 100
    assert payload["progress_bar"].endswith("100%")

    assert fake_collection.delete_calls == [{"source_url": existing_a_url}]
    assert len(fake_collection.upsert_calls) == 1

    upsert_metas = fake_collection.upsert_calls[0]["metadatas"]
    assert upsert_metas
    assert all(meta["source_url"] == existing_a_url for meta in upsert_metas)
    assert all(meta["site_id"] == "local-docs" for meta in upsert_metas)

    updated_state = state_path.read_text(encoding="utf-8")
    assert existing_a_url in updated_state


def test_update_existing_local_documents_skips_unchanged_matches_incrementally(tmp_path):
    source_dir = tmp_path / "incoming"
    docs_dir = source_dir / "docs"
    docs_dir.mkdir(parents=True)

    file_a = docs_dir / "a.md"
    file_a.write_text("A stable", encoding="utf-8")

    page_a = DocPage(
        site_id="candidate",
        site_name="candidate",
        url=file_a.resolve().as_uri(),
        title="a.md",
        content="A stable",
        content_hash=hash_content("A stable"),
        sections=[DocSection(heading="A", level=1, content="A stable")],
    )

    existing_a_url = (tmp_path / "existing" / "docs" / "a.md").resolve().as_uri()
    fake_collection = _FakeCollection(
        metadatas=[
            {
                "source_url": existing_a_url,
                "site_id": "local-docs",
                "site_name": "Local Docs",
                "content_hash": hash_content("A stable"),
            }
        ]
    )

    payload = update_existing_local_documents(
        str(source_dir),
        collection=fake_collection,
        load_local_pages_func=lambda *_args, **_kwargs: [page_a],
        site_index_state_path_func=lambda site_id: tmp_path / f"{site_id}.state.json",
    )

    assert payload["status"] == "no_change"
    assert payload["matched"] == 1
    assert payload["updated"] == 0
    assert payload["changed_pages"] == 0
    assert payload["unchanged_pages"] == 1
    assert fake_collection.delete_calls == []
    assert fake_collection.upsert_calls == []
