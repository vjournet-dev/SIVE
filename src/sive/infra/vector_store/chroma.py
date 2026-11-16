from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chromadb import Collection

_LOGGER = logging.getLogger(__name__)
_EMBEDDING_CONFLICT_MARKER = "embedding function already exists in the collection configuration"


def get_collection(
    chroma_dir: Path | str,
    collection_name: str,
    embedding_model_name: str,
    *,
    chromadb_module: Any,
    get_collection_from_client_func: Callable[..., Collection],
    reset_collection: bool = False,
) -> Collection:
    if isinstance(chroma_dir, Path):
        chroma_dir.mkdir(parents=True, exist_ok=True)
        chroma_path = str(chroma_dir)
    else:
        Path(chroma_dir).mkdir(parents=True, exist_ok=True)
        chroma_path = chroma_dir

    client = chromadb_module.PersistentClient(path=chroma_path)
    return get_collection_from_client_func(
        client,
        collection_name,
        embedding_model_name,
        reset_collection=reset_collection,
    )


def get_collection_from_client(
    client: Any,
    collection_name: str,
    embedding_model_name: str,
    *,
    get_sentence_transformer_embedding_function_func: Callable[[str], Any],
    reset_collection: bool = False,
) -> Collection:
    if reset_collection:
        existing = {c.name for c in client.list_collections()}
        if collection_name in existing:
            client.delete_collection(collection_name)

    embedding_fn = get_sentence_transformer_embedding_function_func(embedding_model_name)

    try:
        return client.get_or_create_collection(name=collection_name, embedding_function=embedding_fn)
    except ValueError as exc:
        if _EMBEDDING_CONFLICT_MARKER not in str(exc):
            raise
        _LOGGER.info(
            "Collection '%s' already exists with a different persisted embedding configuration. "
            "Reusing the persisted collection configuration instead of forcing model '%s'.",
            collection_name,
            embedding_model_name,
        )
        return client.get_collection(name=collection_name)
