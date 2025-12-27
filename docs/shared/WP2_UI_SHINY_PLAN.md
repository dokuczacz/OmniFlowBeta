# WP2 - New UI (Shiny for Python) + mini user login (password) - Plan & TODOs

Date: 2025-12-27
Scope: WP2 UI migration to Shiny (Python) + minimal "login with password" (no OAuth).

## 0) Scope / Inputs / Outputs / Acceptance

### Scope
- Replace/augment the current Streamlit LAB UI with a Shiny dashboard UI.
- Add a minimal user login step (user_id + password) in UI.
- UI must not bypass backend user isolation; UI only sets `X-User-Id`.

### Inputs
- Backend endpoints (source of truth): `tool_call_handler`, storage tools, WP7 indexer outputs, WP9 reporting (local).
- Existing Streamlit UI reference: `frontend/app.py`.
- Tool usage docs: `FUNCTION_CALLS_PLAYBOOK.md`, `AGENT_FUNCTIONS_CATALOG.json`.

### Outputs
- New Shiny UI app folder (to be implemented next): `ui_shiny/` (or similar).
- UI "Login -> Chat" flow producing correct `X-User-Id` headers.
- UI can call `tool_call_handler` reliably on prod/dev.

### Acceptance criteria (MVP)
1) User can log in (user_id + password) and UI uses only that user_id for all calls.
2) Chat calls `POST /api/tool_call_handler` and renders response + basic telemetry.
3) "Runs/Reports" shows last response metadata (runtime_used, tool_calls_count, timings if returned).
4) UI supports `dev|prod` endpoint switch without code changes.
5) No secrets committed (password store remains env/secret).

## 1) "Mini user login" (password) - recommended approach

### Goal
Avoid accidental use of `default` and reduce cross-user mistakes in UI.

### Security model (explicit)
- This is UI-level gating, not OAuth.
- Backend endpoints are still protected by Azure Function keys; if someone has the key, they can call any `user_id`.

### Minimal implementation (v0)
- UI form:
  - `user_id`
  - `password`
- UI validates password locally against one of:
  - Option A (simplest): `UI_SHARED_PASSWORD` (one password for all users)
  - Option B (per user): `UI_USERS_JSON` = JSON mapping `{ "MarioBros": "<hash>", ... }`
- On success:
  - store `active_user_id` in UI session state
  - set `X-User-Id: <active_user_id>` for every request

### TODO decision (needs your pick)
- Which mode: shared password or per-user passwords?
- Where to store secrets for Shiny deployment (env vars / hosting secrets)?

## 2) Migration strategy: "copy/paste Streamlit -> Shiny"

### What to reuse from `frontend/app.py`
- HTTP client session (requests.Session equivalent).
- `BACKEND_URL` configuration (dev/prod).
- Helpers:
  - build endpoint URL (`/api/<function>`)
  - header builder (`X-User-Id`)
  - user_id normalization
  - user bootstrap (optional)

### Shiny concepts (for beginners)
- UI layout: sidebar + tabs.
- State: `reactive.Value` (instead of Streamlit `st.session_state`).
- Events: explicit handlers on input changes / button clicks.
- Outputs: render text/HTML based on reactive state.

## 3) Modules (implementation breakdown)

### M0 - Shiny skeleton (1-2h)
- Create `ui_shiny/app.py` with:
  - sidebar: endpoint + login form
  - tabs: Chat / Agent Control (placeholder) / Runs (placeholder)
- Add `ui_shiny/requirements.txt` (`shiny`, `requests`).

### M1 - Chat MVP (2-4h)
- Port chat history rendering (minimal).
- Call backend `tool_call_handler`:
  - request: `{ "message": "...", "thread_id": "...", "runtime": "responses" }` (runtime optional)
  - headers: `X-User-Id`
- Show:
  - assistant message
  - `runtime_used`, timing fields if returned

### M2 - Login (password) (1-3h)
- Implement Option A or B.
- Block UI until login success.
- Show `users/{user_id}` as visible isolation label.

### M3 - Runs/Reports MVP (1-2h)
- Keep local in UI memory:
  - last N runs (timestamp, status, latency, tool_calls_count)
- Optional: show the last raw backend response JSON for debugging.

### M4 - Context Builder stub (2-4h)
- UI lets user choose:
  - sources: HOT/MOD/COLD later (WP6), for now: blob paths
  - filters: category/tags/time range (optional)
  - limits: max items / max bytes
- For now: call existing tools (`list_blobs`, `read_many_blobs`) and assemble a preview.

### M5 - Streaming + long runs (Phase 2)
- Only after UI MVP is stable.
- Requires backend endpoints (SSE/job) - separate work package.

## 4) TODO list (ordered)

1) Decide auth mode: shared vs per-user passwords.
2) Create `ui_shiny/` skeleton (M0).
3) Port Chat MVP (M1).
4) Add login gate (M2).
5) Add Runs tab (M3).
6) Add Context Builder stub (M4).
7) Document how to run locally + how to deploy Shiny.

## 5) Non-goals (explicit)

- No OAuth / Easy Auth here (future WP8).
- No vector DB / classic RAG (WP3 parked).
- No full streaming/job system in this MVP (separate backend work).

