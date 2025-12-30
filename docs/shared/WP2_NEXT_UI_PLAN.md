# WP2 — Next UI (status + remaining integration)

- Status: active (WP2 done; integration pending)
- Audience: operator + developer
- Scope: connect OmniFlow chat functionality into the preferred Next UI template

## Current status

- OK WP2 “migration from Streamlit to Next.js UI” is done.
- X Remaining: connect the proven chat functionality from `ai-chatbot/` into the preferred UI in `ui_next/`.

## Inputs (existing pieces)

- Backend primary endpoint: `POST /api/tool_call_handler`
- Optional: `POST /api/wp7_indexer_run` (manual indexing)
- Reference implementation (AI chat template):
  - API proxy example: `ai-chatbot/app/api/omni/route.ts`

## Outputs (definition of done)

- `ui_next/` can:
  - send chat messages to the backend (with correct `X-User-Id`)
  - persist `thread_id` per user
  - show a minimal operator debug view (last request/response) so deployments are verifiable without server logs

## Acceptance (minimal e2e)

- Cache hit/miss behavior is visible in backend logs and does not break UI.
- WP7 artifacts are inspectable via the UI (at least by reading tails of `interactions/semantic/index.jsonl`).

## Rollback

- UI-only rollback: redeploy previous UI build (backend contracts unchanged).

