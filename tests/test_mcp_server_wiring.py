import asyncio
import logging
import threading
from types import SimpleNamespace

from sive.app import mcp_server


class _BuildServerFakeCollection:
    def query(self, *args, **kwargs):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    def get(self, *args, **kwargs):
        return {"metadatas": []}

    def delete(self, *args, **kwargs):
        return None


class _BuildServerConflictClient:
    def __init__(self):
        self.persisted_collection = _BuildServerFakeCollection()
        self.calls: list[tuple[str, str]] = []

    def get_or_create_collection(self, name: str, embedding_function):
        self.calls.append(("get_or_create_collection", name))
        raise ValueError(
            "An embedding function already exists in the collection configuration, and a new one is provided. "
            "If this is intentional, please embed documents separately. Embedding function conflict: new: "
            "sentence_transformer vs persisted: default"
        )

    def get_collection(self, name: str):
        self.calls.append(("get_collection", name))
        return self.persisted_collection


def test_build_server_does_not_open_the_collection_at_startup(monkeypatch):
    def open_collection(*args):
        raise AssertionError("the collection must not be opened while building the server")

    monkeypatch.setattr(mcp_server, "_open_collection", open_collection)

    assert mcp_server.build_server(chroma_path="ignored-path") is not None


def test_build_server_warm_up_opens_the_collection_in_background(monkeypatch):
    opened = threading.Event()

    def open_collection(*args):
        opened.set()
        return _BuildServerFakeCollection()

    monkeypatch.setattr(mcp_server, "_open_collection", open_collection)

    mcp_server.build_server(chroma_path="ignored-path", warm_up=True)

    assert opened.wait(timeout=5)


def test_tools_declare_which_calls_clients_can_approve_without_prompting():
    server = mcp_server.build_server(chroma_path="ignored-path")

    annotations = {tool.name: tool.annotations for tool in asyncio.run(server.list_tools())}

    assert all(item is not None for item in annotations.values())
    read_only = {name for name, item in annotations.items() if item.read_only_hint}
    destructive = {name for name, item in annotations.items() if item.destructive_hint}
    assert read_only == {
        "list_indexed_doc_sites",
        "list_documentation_sites_in_database",
        "get_site_sync_status",
        "list_site_sync_status",
        "ingest_status",
        "wait_for_ingest_completion",
        "search_documentation",
        "suggest_documentation_urls",
    }
    assert set(annotations) - read_only == {
        "ingest",
        "ingest_and_register_topic",
        "update_site_differential",
        "update_documentation_source",
        "authenticate_ingest_job",
        "set_ingest_auth_session",
        "set_ingest_auth_config",
        "delete_documentation_site",
    }
    assert destructive == {"delete_documentation_site"}


def test_open_collection_reuses_persisted_collection_on_embedding_conflict(monkeypatch, caplog):
    fake_client = _BuildServerConflictClient()

    monkeypatch.setattr(mcp_server, "chromadb", SimpleNamespace(PersistentClient=lambda path: fake_client))
    monkeypatch.setattr(mcp_server, "apply_hf_token_from_env", lambda: None)
    monkeypatch.setattr(mcp_server, "get_sentence_transformer_embedding_function", lambda _model_name: object())

    with caplog.at_level(logging.INFO, logger="sive.infra.vector_store.chroma"):
        collection = mcp_server._open_collection("ignored-path", mcp_server.DEFAULT_COLLECTION_NAME, "model")

    assert collection is fake_client.persisted_collection
    assert fake_client.calls == [
        ("get_or_create_collection", mcp_server.DEFAULT_COLLECTION_NAME),
        ("get_collection", mcp_server.DEFAULT_COLLECTION_NAME),
    ]
    matching_records = [record for record in caplog.records if "Reusing the persisted collection" in record.message]
    assert len(matching_records) == 1
    assert matching_records[0].levelno == logging.INFO
