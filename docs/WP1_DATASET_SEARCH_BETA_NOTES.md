**Status**: active
- **Scope**: Beta tool-handler data search (manifest-based). No external DBs or prompts.
- **Audience**: operator, developer
- **Inputs / Outputs**:
  - Tool: `dataset_search`
  - Input: `{ user_id, q?, tags_any?, tags_all?, category?, since?, until?, limit?, cursor? }`
  - Output: `{ status, user_id, total, cursor, hits: [{ blob_name, display_name, summary, tags, category, source, updated_at, created_at, size, metadata, score }] }`
- **Acceptance**:
  - Reads `manifests/{user_id}/manifest.json` only.
  - Deterministic sort: `updated_at desc`, `blob_name asc`.
  - Applies filters without external lookups or embeddings.
- **Rollback**: remove tool registration in `backend/tools/__init__.py` and tool handler usage.

# Context and concerns
- Beta tool handler needs a single, deterministic search over user blobs without external databases.
- The manifest is the source of truth; no semantic/indexer usage.
- Must be safe for large accounts: limit results, cursor paging, avoid full blob reads.

# Expected behavior
- Filter logic mirrors Central's manifest search (no full content fetch):
  - `q` in `display_name` or `summary`
  - `tags_any` intersects tags
  - `tags_all` subset of tags
  - `category` exact match (case-insensitive)
  - `since`/`until` window on `updated_at` or `created_at`
- Cursor format: `{updated_at}|{blob_name}` (stable pagination).
- `limit` hard-capped to avoid large responses.

# Implementation sketch (Beta only)
- Service: `backend/dataset_search/service.py`
  - `load_manifest` -> `entries` array
  - normalize tags/category, sort, filter, score
- Tool wrapper: `backend/tools/dataset_search.py`
  - calls service core, returns dict
- Tool registry: `backend/tools/__init__.py` add `dataset_search`

# Follow-ups
- Add unit test: `tests/unit/test_tools_dataset_search.py`
- Optional: Add to `backend/custom_gpt_tools/actions_openapi.json` if HTTP exposure is ever needed.
