import logging

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


def test_build_server_reuses_persisted_collection_on_embedding_conflict(monkeypatch, caplog):
    fake_client = _BuildServerConflictClient()

    monkeypatch.setattr(mcp_server.chromadb, "PersistentClient", lambda path: fake_client)
    monkeypatch.setattr(mcp_server, "apply_hf_token_from_env", lambda: None)
    monkeypatch.setattr(mcp_server, "get_sentence_transformer_embedding_function", lambda _model_name: object())

    with caplog.at_level(logging.INFO, logger="sive.infra.vector_store.chroma"):
        server = mcp_server.build_server(chroma_path="ignored-path")

    assert server is not None
    assert fake_client.calls == [
        ("get_or_create_collection", mcp_server.DEFAULT_COLLECTION_NAME),
        ("get_collection", mcp_server.DEFAULT_COLLECTION_NAME),
    ]
    matching_records = [record for record in caplog.records if "Reusing the persisted collection" in record.message]
    assert len(matching_records) == 1
    assert matching_records[0].levelno == logging.INFO
