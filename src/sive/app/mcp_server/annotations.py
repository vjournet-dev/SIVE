"""Behavior hints advertised with each MCP tool.

Clients use them to approve routine calls without prompting and to always ask before irreversible ones
(for example Codex prompts for tools marked destructive).
"""

from __future__ import annotations

from mcp.types import ToolAnnotations

# Retrieval and status tools never change the index, the job state or the filesystem.
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

# Same guarantee, but the tool reaches the public web.
READ_ONLY_OPEN_WORLD = ToolAnnotations(read_only_hint=True, open_world_hint=True)

# Starting or refreshing ingestion adds or updates indexed documents and never removes a source.
INGESTION = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)

# Handing credentials to a blocked ingestion job.
AUTHENTICATION = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
)

# Removing an indexed source and its raw files cannot be undone.
DESTRUCTIVE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=True,
    open_world_hint=False,
)
