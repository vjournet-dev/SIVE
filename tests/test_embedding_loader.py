import logging

from sive.infra.vector_store import embedding_loader


def test_embedding_local_cache_retry_logs_info_not_warning(monkeypatch, caplog):
    calls: list[dict[str, object]] = []

    def _embedding_function(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise OSError("offline")
        return object()

    monkeypatch.setattr(
        embedding_loader.embedding_functions,
        "SentenceTransformerEmbeddingFunction",
        _embedding_function,
    )
    monkeypatch.setattr(embedding_loader, "apply_hf_token_from_env", lambda: None)
    embedding_loader._EMBEDDING_FN_CACHE.clear()

    with caplog.at_level(logging.INFO, logger=embedding_loader.__name__):
        embedding_loader.get_sentence_transformer_embedding_function("test-model")

    retry_records = [record for record in caplog.records if "online load failed" in record.message]
    assert len(retry_records) == 1
    assert retry_records[0].levelno == logging.INFO
    assert calls == [
        {"model_name": "test-model"},
        {"model_name": "test-model", "local_files_only": True},
    ]