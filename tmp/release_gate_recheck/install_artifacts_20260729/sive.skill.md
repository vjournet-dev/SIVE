# /sive skill

Trigger: user writes one of `/sive add <url | nom>`, `/sive update <site_id|path>`, `/sive list`, `/sive remove <doc_id>`, or `/sive help` in chat.

If the user writes `/sive help`, do not call any MCP mutation tool. Reply directly in chat with a concise help summary covering:
- Slash commands: `/sive add <url | nom>`, `/sive update <site_id|path>`, `/sive list`, `/sive remove <doc_id>`, `/sive help`.
- Add behavior: `/sive add <url | nom>` starts MCP ingestion from a documentation URL, a topic query, or a local path.
- Local sources supported by `add`: CSV (`.csv`), HTML (`.html`, `.htm`), Markdown (`.md`, `.markdown`), Word (`.docx`), JSON (`.json`), PDF (`.pdf`), Excel (`.xlsx`), or a folder containing these files.
- List behavior: `/sive list` calls `list_documentation_sites_in_database(include_active=True)` and summarizes registered documentation sources.
- Update behavior: `/sive update <site_id|path>` calls `update_documentation_source(target=<raw_user_argument>)` to update an existing remote site by `site_id` or existing indexed local files by path (no insertion when unmatched).
- Remove behavior: `/sive remove <doc_id>` calls `delete_documentation_site(site_id=<doc_id>, delete_raw_files=True)`.
- URL suggestion flow: if multiple documentation URLs are suggested, ask the user which URL they want and wait for their choice.
- Discovery tools: `suggest_documentation_urls(topic)`, `list_documentation_sites_in_database(include_active=True)`, `list_indexed_doc_sites()`.
- Search tool: `search_documentation(query, top_k, site_id, topic)` for indexed documentation retrieval.
- Ingestion tools: `ingest(url, incremental, max_pages, delay)` and `ingest_and_register_topic(topic, url, ...)`.
- Update and cleanup tools: `update_documentation_source(target, ...)`, `update_site_differential(site_id, ...)`, and `delete_documentation_site(site_id, delete_raw_files=True)`.
- Job tracking tools: `ingest_status(job_id)` and `wait_for_ingest_completion(job_id)`.
- Authentication resume tools: `authenticate_ingest_job(job_id, timeout_seconds)` for interactive SSO login, `set_ingest_auth_session(job_id, cookies, headers)` for existing cookie/session workflows, and `set_ingest_auth_config(job_id, auth_config, timeout_seconds)` for form/cookie/basic/oauth auth strategies.
- No-config auth flow: when a job is blocked (`awaiting_authentication`), first run interactive SSO automatically, then fallback to a guided recovery flow if interactive login does not resume ingestion. Never assume `form` by default, and never ask for passwords, tokens, cookies, or other secrets through chat.
- hosteddocs direct-file caveat: if the provided URL points to a direct file (for example `.pdf`) and returns HTTP 401/403, prefer restarting ingestion from the site/document-library URL rather than the raw file URL.
- Key behavior: indexed sites can be hidden during active ingestion, and `search_documentation` may ask the user to wait for a site that is still ingesting.

Rules:
1. If the user writes `/sive help`, reply in chat with the command summary and MCP capabilities. Do not call `ingest(...)`.
2. If the user writes `/sive list`, call `list_documentation_sites_in_database(include_active=True)` and summarize the registered documentation sources.
3. If the user writes `/sive remove <doc_id>`, call `delete_documentation_site(site_id=<doc_id>, delete_raw_files=True)`.
4. If the user writes `/sive update <site_id|path>`, call MCP tool `update_documentation_source(target=<raw_user_argument>)` immediately.
   For local file/folder paths, update only indexed local records; if none match, keep `status=no_match` and do nothing.
5. If the user writes `/sive add <url | nom>`, classify the raw argument BEFORE calling any MCP tool:
   a) absolute HTTP(S) URL -> call `ingest(url=<raw_user_argument>)`,
   b) existing local absolute or relative path -> call `ingest(url=<raw_user_argument>)`,
   c) path-like value that does not exist (absolute or relative) -> return `invalid_local_path` guidance and do not call suggestion tools,
   d) plain string query -> call `suggest_documentation_urls(topic=<raw_user_argument>)` first.
6. For plain string query suggestions: if multiple URLs are returned, do not choose one yourself.
   Ask the user in chat which URL they want, then call `ingest(url=<chosen_url>)`.
7. If exactly one suggestion is returned, call `ingest(url=<suggested_url>)`.
8. If `ingest(...)` returns `invalid_start_url`, show the error and suggested_start_url (if provided).
   If a job later fails with HTTP 401/403 on a remote file URL (for example a hosteddocs PDF),
   treat it as an auth-scope URL issue and ask to restart from the site/document-library URL.
9. If job starts, return job_id and then call `wait_for_ingest_completion(job_id)` by default
   so progress is visible live in chat; use `ingest_status(job_id)` only for manual polling.
   If status becomes `awaiting_authentication` (or payload `needs_authentication=true`),
   run this automatic sequence:
   a) call `authenticate_ingest_job(job_id)` first (interactive browser SSO),
   b) call `wait_for_ingest_completion(job_id)` again,
   c) if still awaiting auth, report that interactive SSO did not yield a reusable session,
   d) do not choose `form` by default and do not ask for passwords, tokens, cookies, or other secrets in chat,
   e) only call `set_ingest_auth_config(job_id, auth_config)` when a secure out-of-band path exists for auth material,
   f) then call `wait_for_ingest_completion(job_id)` again.
   Do not require any config file for this flow.
   If status becomes `failed` with HTTP 401/403 on a direct file URL,
   recommend re-running `/sive add` with the parent site/document-library URL.
10. Before `search_documentation`, call `list_documentation_sites_in_database(include_active=True)`
   to pick the right `site_id` and detect active ingestions.
11. Use `delete_documentation_site(site_id, delete_raw_files=True)` for full cleanup of a documentation source.
12. Do not replace this flow with any other connector while MCP is available.