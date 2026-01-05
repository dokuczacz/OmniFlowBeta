# Beta backend endpoint cleanup (instructions)

## Scope

Goal: reduce exposed Azure Function HTTP endpoints while keeping the app behavior the same for the local UI (`/api/tool_call_handler`) and WP7 indexing (`wp7_indexer_timer`).

## Current UI contract

- UI calls only: `POST /api/tool_call_handler` (see `ai-chatbot/components/mvp-shell.tsx`).
- Tool execution is in-process via `tools.dispatch_tool(...)` from `backend/tool_call_handler/__init__.py` (fallback to proxy is best-effort).

## Recommended endpoint policy

**Keep enabled**

- `backend/tool_call_handler/function.json` (UI entrypoint)
- `backend/wp7_indexer_timer/function.json` (timer trigger)
- `backend/wp7_indexer_run/function.json` (optional; keep while debugging WP7)

**Disable (obsolete / broken / not used by UI)**

- `backend/gmail_oauth_callback/function.json` (was throwing `No module named 'service'`)
- `backend/oauth_email/function.json` (not used by UI)
- `backend/custom_bridge/function.json` (not used by UI; legacy)
- `backend/get_interaction_history/function.json` (deprecated; not used by UI)
- `backend/proxy_router/function.json` (no longer needed when tool dispatch is in-process)
- `backend/save_interaction/function.json` (tool handler logs in-process; endpoint no longer needed)

**Disable (helper endpoints; keep code but not HTTP)**

These tools are executed in-process via `tools/` and do not need their own HTTP triggers:

- `backend/add_new_data/function.json`
- `backend/get_current_time/function.json`
- `backend/get_filtered_data/function.json`
- `backend/list_blobs/function.json`
- `backend/read_blob_file/function.json`
- `backend/read_many_blobs/function.json`
- `backend/remove_data_entry/function.json`
- `backend/update_data_entry/function.json`
- `backend/upload_data_or_file/function.json`
- `backend/manage_files/function.json`

## How to disable an endpoint (reversible)

1. Edit the function’s `function.json`.
2. Add a top-level flag: `"disabled": true,` (first property).
3. Restart the `func` host.

Rollback: remove `"disabled": true` and restart.

## Acceptance criteria

- UI chat works via `POST /api/tool_call_handler` (no `(Error) action is required`).
- `save_interaction` still writes new `interactions/INT_*.json` + updates `interactions/index.jsonl` (tool handler logs interactions in-process).
- WP7 timer continues running (or is explicitly disabled separately if Azurite isn’t running).

