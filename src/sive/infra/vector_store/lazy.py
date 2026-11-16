from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

_LOGGER = logging.getLogger(__name__)


class LazyCollection:
    """Collection proxy that opens the real vector-store collection on first use.

    Importing chromadb/torch and loading the embedding model takes far longer than the startup timeouts of
    MCP clients. The server therefore answers its handshake first and opens the collection afterwards, either
    in the background (``warm_up``) or on the first tool call that needs it.
    """

    def __init__(self, factory: Callable[[], Any]) -> None:
        self._factory = factory
        self._lock = threading.Lock()
        self._collection: Any = None

    @property
    def is_open(self) -> bool:
        return self._collection is not None

    def resolve(self) -> Any:
        collection = self._collection
        if collection is not None:
            return collection
        with self._lock:
            if self._collection is None:
                self._collection = self._factory()
            return self._collection

    def warm_up(self) -> threading.Thread:
        """Open the collection in a daemon thread so the first real call does not pay the loading cost."""
        thread = threading.Thread(target=self._warm_up, name="sive-warm-up", daemon=True)
        thread.start()
        return thread

    def _warm_up(self) -> None:
        try:
            self.resolve()
        except Exception:  # a failed warm-up is retried on the first real use
            _LOGGER.warning("Background warm-up failed; the collection will be opened on first use.", exc_info=True)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.resolve(), name)
