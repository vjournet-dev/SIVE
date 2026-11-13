from __future__ import annotations

import logging
from threading import Lock
from typing import Any

from chromadb.utils import embedding_functions

from .hf_auth import apply_hf_token_from_env

_LOGGER = logging.getLogger(__name__)
_CACHE_LOCK = Lock()
_EMBEDDING_FN_CACHE: dict[str, Any] = {}


def get_sentence_transformer_embedding_function(model_name: str) -> Any:
    """Return a cached Chroma embedding function for a sentence-transformers model.

    Strategy:
    - Reuse one embedding function instance per model in the current process.
    - First try normal loading (network + local cache).
    - If that fails, retry with local_files_only=True to avoid extra network attempts
      when the model is already available in local cache.
    """
    with _CACHE_LOCK:
        cached = _EMBEDDING_FN_CACHE.get(model_name)
        if cached is not None:
            _LOGGER.info("Embedding model cache hit for '%s'.", model_name)
            return cached

        apply_hf_token_from_env()
        _LOGGER.info("Embedding model cache miss for '%s'. Loading model.", model_name)

        try:
            embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
            _LOGGER.info("Embedding model '%s' loaded (online/cache mode).", model_name)
        except Exception as exc:  # noqa: BLE001 - fallback to local-only load when online/cache load fails
            _LOGGER.info(
                "Embedding model '%s' online load failed (%s). Retrying with local_files_only=True.",
                model_name,
                exc,
            )
            embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=model_name,
                local_files_only=True,
            )
            _LOGGER.info("Embedding model '%s' loaded from local cache (offline mode).", model_name)

        _EMBEDDING_FN_CACHE[model_name] = embedding_fn
        return embedding_fn