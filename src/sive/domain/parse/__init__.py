"""Parse domain implementation and facades."""

from __future__ import annotations

from .loader import (
    SUPPORTED_LOCAL_FILE_EXTENSIONS,
    SUPPORTED_REMOTE_FILE_EXTENSIONS,
    load_local_pages,
    load_remote_pages,
)

__all__ = [
    "SUPPORTED_LOCAL_FILE_EXTENSIONS",
    "SUPPORTED_REMOTE_FILE_EXTENSIONS",
    "load_local_pages",
    "load_remote_pages",
]
