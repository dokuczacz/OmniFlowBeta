Backend (Azure Functions) lives here. This `backend/` folder is the **Function App root** (contains `host.json` and `function_app.py`).

Key entry points:
- `tool_call_handler/` (main orchestrator; Responses tool-loop)
- `wp7_indexer_timer/` + `wp7_indexer_run/` (semantic indexer; batch-first)
- `read_many_blobs/` (multi-read helper for agents; reduces tool-call overhead)

Local config:
- Start from `backend/local.settings.template.json`
- Keep secrets only in `backend/local.settings.json` (ignored by git)
