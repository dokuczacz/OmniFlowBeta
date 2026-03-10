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
- See `docs/shared/ENVIRONMENT_VARIABLES.md` for a copy/paste-ready catalog of required App Service settings and secret placeholders.

## Future `config.json` surface (WP6/WP7)

To reduce the number of manually updated App Settings, WP6/WP7 are preparing a `config.json` that can live next to the operator UI (for example under `ui_next/` or in a shared config repo/blob). The intention is to make tuning UI-friendly and centrally managed.

**What it stores**
- Grouped, UI-editable tuning values (example shape):
  - `wp6`: FAST/DEEP limits, cache TTLs, routing knobs
  - `wp7`: batching thresholds, allowed categories, dedup window
- Optional feature gates (future): `wp6.enabled`, `wp7.enabled`, `wp6.deepMode`, etc.

**Who edits it**
- Operator / release engineer via Next.js operator UI (not developers editing App Settings by hand).

**How it replaces envs**
- Runtime remains compatible with current env-driven defaults (`backend/local.settings.template.json`).
- `config.json` should be treated as an overlay: only keys present in the JSON override defaults.
- Rollback is deterministic: revert `config.json` (or point UI back to previous version) and the runtime returns to env defaults.

Keep `docs/shared/ENVIRONMENT_VARIABLES.md` as the authoritative catalog of environment keys and secrets even after `config.json` is introduced; the JSON is for operational tuning, not for storing secrets.

## Key environment categories (sorted)

| Category | Key vars | Purpose |
| --- | --- | --- |
| **OpenAI / Responses** | `OPENAI_API_KEY`, `OPENAI_ASSISTANT_ID`, `OPENAI_PROMPT_ID`, `OPENAI_VECTOR_STORE_ID`, `OPENAI_API_BASE`, `LLM_RUNTIME`, `OPENAI_CONTEXT_BUILDER_PROMPT_ID`, `RESPONSES_INCLUDE_TOOLS` | Select which runtime/prompt IDs you use for Responses/Assistants and enable tool calls. |
| **Azure Functions** | `FUNCTION_URL_BASE`, `AZURE_PROXY_URL`, `FUNCTION_CODE_*` (per endpoint), `HANDLES_CACHE_TTL_SECONDS` | Control host URL, proxy routing, and function-level keys. |
| **WP6 (Context Builder)** | `WP6_DEFAULT_CONTEXT_MODE`, `WP6_FAST_MAX_INPUT_TOKENS`, `WP6_FAST_MAX_SOURCES`, `WP6_FAST_MAX_RAW_BYTES`, `WP6_DEEP_MAX_PACK_TOKENS`, `WP6_DEEP_MAX_CANDIDATE_SOURCES`, `WP6_DEEP_MIN_SEMANTIC_SELECTED`, `WP6_DEEP_MIN_SEMANTIC_CANDIDATES`, `CONTEXTPACK_TTL_SECONDS` | Tune FAST/DEEP routing buckets plus cache TTLs. |
| **WP7 (Semantic indexer)** | `WP7_ENABLED`, `WP7_INDEXER_MODE`, `WP7_INDEXER_USER_IDS`, `WP7_TARGET_BATCH_TOKENS`, `WP7_HARD_MIN_BATCH_TOKENS`, `WP7_MAX_WAIT_SECONDS`, `WP7_MAX_ITEMS_PER_RUN`, `WP7_MAX_OUTPUT_TOKENS_PER_ITEM`, `WP7_ALLOWED_CATEGORIES`, `WP7_UNCATEGORIZED_CONFIDENCE_LT`, `OPENAI_INDEXER_PROMPT_ID`, `OPENAI_INDEXER_MODEL` | Configure batching thresholds, allowed categories, and indexer prompt/model. |
| **Feature toggles** | `DEBUG_TOOL_CALL_HANDLER`, `ENABLE_SAVE_INTERACTION`, `WP7_ENABLED_FORCED`, `WP8_ENABLED`, `WP11_ENABLED` | Gate new behavior, control logging, and disable pricey flows during rollouts. |

Keep these values synchronized across `.env.local`, Azure App settings, and any UI hosts so each environment behaves consistently.

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

### Custom GPT schema import

- Use the raw URL `https://raw.githubusercontent.com/dokuczacz/OmniFlowBeta/main/docs/shared/custom_bridge_openapi.json` when importing the OpenAPI tool in GPT Builder.
- For broad end-to-end testing (Blob CRUD, file ops, history, plus bridge), import `https://raw.githubusercontent.com/dokuczacz/OmniFlowBeta/main/backend/custom_gpt_tools/actions_openapi.json` instead.
- For single-endpoint quasi-MCP mode (recommended for both Custom GPT and native UI), import `https://raw.githubusercontent.com/dokuczacz/OmniFlowBeta/main/docs/shared/tool_call_handler_openapi.json` and call only `/api/tool_call_handler`.
- In the authentication dialog pick **API key**, store the function key there, choose **Header** → `x-functions-key`, and avoid putting secrets directly into the JSON.
- Custom GPT should always call `ensure_authorized` first; if the reply has `authorized:false`, open the `authorize_url`, complete consent, then repeat `ensure_authorized` before Gmail actions.
- If you see `404` with `path: /custom_bridge`, re-import the schema: the correct tool endpoint is `/api/custom_bridge` under the Function App host.

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

