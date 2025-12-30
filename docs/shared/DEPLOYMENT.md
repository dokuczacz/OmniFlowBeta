# Deploying OmniFlow Beta

- Status: active
- Audience: operator
- Scope: backend (Azure Functions) + UI (Next.js); Streamlit is legacy

## Environment configuration

- Copy `.env.example` to an ignored local file (e.g. `.env.local`) and fill secrets.
- For Azure deployments, mirror the same key/value pairs in:
  - Azure Function App configuration
  - your UI hosting environment (Next.js)
- Keep function codes secret (`FUNCTION_CODE_*`). Rotate them via Azure Portal when needed.

## Publish the backend (Azure Functions)

1. Install deps: `pip install -r backend/requirements.txt`
2. Local smoke: `cd backend && func start`
3. Publish:
   - `cd backend`
   - `func azure functionapp publish <YOUR_FUNCTION_APP_NAME> --python`
4. Verify endpoints respond `200` and honor `X-User-Id`:
   - `POST /api/tool_call_handler`
   - `POST /api/save_interaction`
   - `POST /api/read_many_blobs`

## Publish the UI (Next.js)

Primary UI lives in `ui_next/`.

- Configure the backend base URL in your UI host (example: `OMNIFLOW_BACKEND_URL` if your UI proxy uses it).
- Verify the UI sends `X-User-Id` and correctly persists `thread_id` per user.

## Legacy UI (Streamlit)

Streamlit in `frontend/` is legacy/LAB. Use only if you still need the public Streamlit demo.

## WP6/WP7 deployment notes (semantics + context)

- WP6 Context Builder docs: `docs/workflow/wp6_context_builder/README.md`
- WP7 Semantic Indexer docs: `docs/WP7_Indexer_Batch.md`

Recommended verification in a deployed environment:

- After a chat turn, `save_interaction` succeeds and the user’s namespace is updated.
- WP7 produces semantic artifacts + manifest lines under:
  - `users/{user_id}/interactions/semantic/`
  - `users/{user_id}/interactions/semantic/index.jsonl`

## Rollback paths (config-based)

- Disable WP7 processing: set `WP7_ENABLED=0`
- Disable WP6 deep routing: set `WP6_DEFAULT_CONTEXT_MODE=FAST` (or disable builder integration in your feature gate if present)
- UI rollback: redeploy previous UI build only (no backend rollback needed if contracts unchanged)

