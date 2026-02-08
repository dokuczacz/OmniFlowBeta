# Goal
Stabilize OmniFlowBeta after refactor using only findings from logs dated 2026-02-08, eliminate noisy pseudo-errors, and restore deterministic assistant response flow.

# Inputs and Context
- Source logs only:
  - tmp/logs/func_20260208_172133.log
  - tmp/logs/azurite_20260208_172133.log
  - tmp/logs/azurite_debug_20260208_172133.log
  - tmp/logs/ui_20260208_172133.log
- Critical observed lines (func log):
  - "Tool dispatch not available: read_blob_file/read_many_blobs"
  - "proxy_router ... action=read_blob_file, status=404"
  - "POST to proxy failed: 404 ... /api/proxy_router"
  - "Invalid schema for function 'get_current_time' ... Missing 'user_id'"
  - high-frequency "TOOL_CALL_HANDLER start"

# Acceptance (observable signals + exact commands)
1) No runtime schema 400 for inline tools
- Command:
  - rg -n "Invalid schema for function|invalid_function_parameters" tmp/logs/func_*.log
- Pass: no matches after a fresh run.

2) Tool dispatch path is explicit and non-contradictory
- Command:
  - rg -n "Tool dispatch not available|falling back to legacy dispatch path|proxy_router: backend_call action=(read_blob_file|read_many_blobs), status=" tmp/logs/func_*.log
- Pass:
  - if fallback is used, no ERROR-level "Tool error ... not available" for successful proxy calls.
  - status=200 lines for read_blob_file/read_many_blobs in normal flow.

3) Bootstrap state behaves as first-run info, not failure storm
- Command:
  - rg -n "handles.json|File not found" tmp/logs/func_*.log
- Pass: at most one first-run miss per user/session, followed by successful create/read.

4) Assistant response path returns user-facing content (not manifest dump)
- Command:
  - run local chat smoke and verify UI output for 2 sample prompts.
- Pass: assistant message contains formatted reply sections, not raw manifest JSON.

# Plan (3-7 steps, smallest first)
1. Lock regression baseline from 08.02 logs
- Extract exact failure signatures and map each to code path/function.
- Output artifact: tmp/diag_2026_02_08_signatures.md

2. Fix inline tool schema builder (P0)
- Ensure every generated tool schema satisfies API strictness:
  - required must be present and include all keys in properties when strict mode expects full coverage.
- Start with get_current_time and then validate all catalog tools.

3. Repair dispatch bridge semantics (P0)
- Keep fallback path functional, but stop emitting false INTERNAL_ERROR when fallback succeeds.
- Error-level only when both in-process and fallback paths fail.

4. Normalize proxy error taxonomy (P1)
- Distinguish transport-level 404 from domain "missing blob" 404 in logs and envelopes.
- Return deterministic error code contract (e.g., RESOURCE_NOT_FOUND vs PROXY_ROUTE_NOT_FOUND).

5. First-run bootstrap hardening (P1)
- Initialize handles/index files lazily and idempotently.
- Treat expected first absence as INFO and continue flow.

6. Poll/retry guardrails (P1)
- Add guard against duplicate concurrent polling on same conversation/run.
- Add explicit reason tags in logs: progress_poll, tool_retry, run_retry.

7. Focused tests + smoke gates (P0/P1)
- Add tests for:
  - schema completeness for all inline tools
  - dispatch fallback behavior (success + dual-fail)
  - first-run bootstrap sequence
  - one end-to-end local smoke covering assistant message rendering

8. Stateless continuity switch: disable `last_response` continuation (P1, gated)
- Current state allows `previous_response_id` continuation inside responses loop.
- Keep it ON only during stabilization to avoid changing two variables at once.
- After positive focused tests + smoke (steps 1-7), switch to strict stateless:
  - no persisted `responses_last_response_id`
  - no `previous_response_id` in request path
  - no `conversation` carry-over from previous turns
- Verify no regression in tool loop completion and assistant output quality.

# Commands (exact with working directory)
Working directory:
- C:\AI memory\NewHope\OmniFlowBeta

Suggested commands:
- pwsh -NoLogo -NoProfile -File .\scripts\run_local.ps1
- rg -n "Invalid schema for function|invalid_function_parameters|Tool dispatch not available|POST to proxy failed|handles.json" .\tmp\logs\func_*.log
- pytest -q tests/toolhandler/test_tool_schema_contract.py
- pytest -q tests/toolhandler/test_dispatch_fallback.py
- pytest -q tests/toolhandler/test_bootstrap_first_run.py

# Validation (tests / manual checks)
L0 metadata:
- Confirm new logs file generated for func/ui/azurite under tmp/logs.

L2 focused tests:
- tool schema contract test
- dispatch fallback test
- first-run bootstrap test

L2 manual smoke:
- Send 2 user prompts from UI.
- Verify no raw manifest JSON appears in assistant response.

L2 stateless gate (post-green only):
- Confirm logs/trace do not show request-time continuation keys (`previous_response_id`, restored conversation carry-over) after the switch.
- Confirm first-turn behavior still reaches tools and returns user-facing answer.

# Recovery (idempotence, retry, rollback)
- If schema fix breaks older tools, toggle strict generation via feature flag and log warning.
- If dispatch bridge changes regress, keep legacy path as default and shadow-run registry path.
- If bootstrap migration fails, recreate per-user handles/index from deterministic template.

# Notes (decisions + rationale, append-only)
- Decision: prioritize schema builder and dispatch semantics before prompt/content tuning; current blocker is transport/contract stability.
- Decision: scope limited to 2026-02-08 logs only, per operator instruction.
- Decision: `last_response` / `previous_response_id` disconnection is tracked as a separate rollout point and executed only after positive tests.
- 2026-02-09: Implemented dispatch import hardening in `backend/tool_call_handler/__init__.py` (remove `backend/tools` shadow path, enforce `backend` root), which removed legacy fallback import errors (`add_new_data.service`).
- 2026-02-09: Hardened inline tool schema normalization so object schemas always carry `required` aligned with `properties` (prevents Responses API 400 for missing required keys).
- 2026-02-09: E2E smoke with active agent via `POST /api/omni` passed for 3-turn conversation on `user_id=MarioBros`; backend log `tmp/logs/func_20260209_000024.log` shows no `Invalid schema`, no `Tool dispatch not available`, and no 500 in the tested flow.

# Why tests passed before despite runtime failure
- Existing tests likely covered unit/contract paths but did not execute full local runtime with:
  - inline tools schema serialization as sent to OpenAI
  - registry->legacy dispatch mixed path under concurrent polling
  - thread/proxy first-run bootstrap conditions
- Action: add integration smoke gate that asserts real API payload validity and response shape.

# Git hygiene
- Inspect only:
  - git status -sb
  - git diff --stat
- Stage explicit files only when implementation starts.
