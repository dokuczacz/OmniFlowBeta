# GET, Tags Search, Vector Memory, Multi-Agent Plan

## Scope
- Expand fast GET endpoints (no side effects) for blobs and context.
- Add tag-based search helper (exact/regex) in addition to semantic search.
- Outline vector memory pipeline on existing blob data.
- Sketch multi-agent routines (cleaner, adherence, task manager, summarizer).

## GET Endpoints (read-only)
1) list_blobs(prefix=None, max_results=200, continuation_token=None)
   - Purpose: fast discovery; supports pseudo-folders and pagination.
2) head_blob_exists(file_name)
   - Purpose: boolean existence check without download.
3) get_blob_meta(file_name)
   - Purpose: size, etag, last_modified, content_type, md5; no body.
4) read_blob_file(file_name, offset=0, length=None)
   - Purpose: range reads for large files; offset/length optional.
5) search_blob_names(query, prefix=None)
   - Purpose: client-side name filter; quick find.
6) search_blob_content(file_name, regex)
   - Purpose: regex scan on text files (small/medium); returns matches with line numbers.
7) get_daily_context(date)
   - Purpose: aggregate TM/PS/LO entries for a date window; read-only summary.
8) summarize_blob(file_name, max_chars=4000)
   - Purpose: return head/tail preview for large files.

## Tag-Based Search (non-semantic)
- Endpoint: search_by_tags(tags: list[str], match="any|all", category=None)
- Logic: load index (or file), filter entries where tags satisfy match; returns IDs + snippets.
- Storage: keep tag index in JSON (e.g., tags_index.json) refreshed daily; fallback to on-demand scan if missing.

## Vector Memory (semantic path)
- Source: existing blob docs (JSON/MD/TXT) with metadata {source, category, timestamp, task_id, tags}.
- Chunking: markdown-aware, 512-1024 tokens, 10-20% overlap.
- Embeddings: OpenAI text-embedding-3-small (or Azure equivalent); batch by chunk.
- Store: pgvector or Azure Cognitive Search vectors; dev fallback FAISS.
- Index state: vector_index_state.json tracking etag/last_modified per file; re-embed when changed.
- Query endpoint: semantic_search(query, top_k=8, filter={category, date_range, tags}).
- Context pack: context_pack(query) → semantic_search + dedup + ranked chunks with citations.

## Multi-Agent Routines (timer-driven)
- Cleaner (nightly): validate JSON schema, fix whitespace/ids; writes report blob only.
- Adherence Checker (daily): compare current files to system rules; outputs drift report.
- Task Manager (hourly): scan TM/PS, flag overdue/soon, align tasks→goals; writes agenda.
- Summarizer (on-demand/weekly): produce TL;DR into ML category.
- All agents use GETs + minimal writes (reports), keeping costs low.

## Suggested Build Order
1) Implement GET helpers: head_blob_exists, get_blob_meta, read_blob_file(offset/length), search_blob_names.
2) Add search_by_tags endpoint with JSON index; fallback to on-demand scan.
3) Extend list_blobs with prefix/pagination; add summarize_blob (head/tail preview).
4) Stand up semantic_search stub; then wire embedding + vector store with index_state tracking.
5) Add get_daily_context aggregator; then multi-agent timers (cleaner → adherence → task manager → summarizer).

## Notes
- Keep GET endpoints pure (no writes); favor HEAD/range for speed.
- For regex search, enforce max file size limit (e.g., 1 MB) to avoid heavy reads.
- For tag index refresh, run via timer once/day; store last build timestamp.
- For vector freshness, compare blob etag/last_modified before re-embedding.
- Multi-agent reports should include summary + actionable items; avoid rewriting source files automatically.
