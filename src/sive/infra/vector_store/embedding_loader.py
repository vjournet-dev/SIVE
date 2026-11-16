from __future__ import annotations

import logging
from threading import Lock
from typing import Any

from .hf_auth import apply_hf_token_from_env

_LOGGER = logging.getLogger(__name__)
_CACHE_LOCK = Lock()
_EMBEDDING_FN_CACHE: dict[str, Any] = {}

DEFAULT_EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def get_sentence_transformer_embedding_function(model_name: str) -> Any:
    """Return a cached Chroma embedding function for a sentence-transformers model.

    Strategy:
    - Reuse one embedding function instance per model in the current process.
    - Load from the local Hugging Face cache first, without any network request.
    - Download the model only when it is not cached yet.

    An online load sends a request per model file to the Hub even when everything is cached, which costs
    seconds on a good network and minutes behind a filtering proxy. Not checking for newer revisions also
    keeps query embeddings consistent with the vectors already indexed.
    """
    with _CACHE_LOCK:
        cached = _EMBEDDING_FN_CACHE.get(model_name)
        if cached is not None:
            _LOGGER.info("Embedding model cache hit for '%s'.", model_name)
            return cached

        # Imported here: chromadb and sentence-transformers are too slow to load at server startup.
        from chromadb.utils import embedding_functions

        apply_hf_token_from_env()
        _LOGGER.info("Embedding model cache miss for '%s'. Loading model.", model_name)

        try:
            embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=model_name,
                local_files_only=True,
            )
            _LOGGER.info("Embedding model '%s' loaded from the local cache.", model_name)
        except Exception as exc:  # noqa: BLE001 - any local-cache failure falls back to a download
            _LOGGER.info(
                "Embedding model '%s' is not in the local cache (%s). Downloading it once.",
                model_name,
                exc,
            )
            embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
            _LOGGER.info("Embedding model '%s' downloaded and loaded.", model_name)

        _EMBEDDING_FN_CACHE[model_name] = embedding_fn
        return embedding_fn