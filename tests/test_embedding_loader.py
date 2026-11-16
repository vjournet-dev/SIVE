import logging

from chromadb.utils import embedding_functions

from sive.infra.vector_store import embedding_loader


def _patch_embedding_function(monkeypatch, *, local_available: bool) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def _embedding_function(**kwargs):
        calls.append(kwargs)
        if kwargs.get("local_files_only") and not local_available:
            raise OSError("not in local cache")
        return object()

    monkeypatch.setattr(embedding_functions, "SentenceTransformerEmbeddingFunction", _embedding_function)
    monkeypatch.setattr(embedding_loader, "apply_hf_token_from_env", lambda: None)
    embedding_loader._EMBEDDING_FN_CACHE.clear()
    return calls


def test_embedding_cached_model_loads_without_network(monkeypatch):
    calls = _patch_embedding_function(monkeypatch, local_available=True)

    first = embedding_loader.get_sentence_transformer_embedding_function("test-model")
    second = embedding_loader.get_sentence_transformer_embedding_function("test-model")

    assert first is second
    assert calls == [{"model_name": "test-model", "local_files_only": True}]


def test_embedding_missing_model_is_downloaded_with_info_log(monkeypatch, caplog):
    calls = _patch_embedding_function(monkeypatch, local_available=False)

    with caplog.at_level(logging.INFO, logger=embedding_loader.__name__):
        embedding_loader.get_sentence_transformer_embedding_function("test-model")

    download_records = [record for record in caplog.records if "not in the local cache" in record.message]
    assert len(download_records) == 1
    assert download_records[0].levelno == logging.INFO
    assert calls == [
        {"model_name": "test-model", "local_files_only": True},
        {"model_name": "test-model"},
    ]