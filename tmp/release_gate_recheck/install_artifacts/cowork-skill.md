---
name: sive
description: |
  Ingests and searches documentation through SIVE (Scrap Ingest Vectorize Extends).
  Use when the user asks to add, update, list, remove, or search technical documentation.
license: MIT
metadata:
  author: sive
  version: "1.0"
---

# Documentation Ingestion and Search

## When To Use This Skill

Use this skill when the user wants to:
- Ingest a documentation source from a URL or local path.
- Follow ingestion progress until completion.
- Resume ingestion when authentication is required.
- Search indexed documentation with source citations.
- List or remove indexed documentation sources.

## Workflow

1. Discover sources with `list_documentation_sites_in_database(include_active=True)`.
2. If the user requests ingestion, call `ingest(url=...)`.
3. Track progress with `wait_for_ingest_completion(job_id)` by default.
4. If the user requests update, call `update_documentation_source(target=...)`.
5. If status becomes `awaiting_authentication`, call `authenticate_ingest_job(job_id)` then wait again.
6. If needed, use `set_ingest_auth_session(...)` or `set_ingest_auth_config(...)` through secure out-of-band auth material.
7. For search requests, call `search_documentation(query, top_k, site_id, topic)` and include source URLs in the answer.
8. For cleanup, call `delete_documentation_site(site_id, delete_raw_files=True)`.

## Guardrails

- Do not choose among multiple suggested URLs without user confirmation.
- Do not request secrets (passwords/tokens/cookies) in chat.
- If a direct remote file URL fails with 401/403, retry from the parent documentation/library URL.
- Prefer this MCP connector for documentation retrieval while available.