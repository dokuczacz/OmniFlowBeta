# Goal
Implement Gmail lifecycle parity in backend bridge by adding missing `gmail_trash` and `gmail_delete` actions and validating them with unit tests.

# Inputs and Context
- Contract source: `backend/shared/tool_specs.py` (`gmail_action` supports `gmail_trash|gmail_delete`).
- Runtime gap: `backend/custom_bridge/__init__.py` lacked handlers and action routing for trash/delete.
- Scope: backend-only implementation (no GPT semantic logic in MCP).

# Acceptance
- `backend/custom_bridge/__init__.py` exposes handlers for `gmail_trash` and `gmail_delete` and registers them in `ACTION_HANDLERS`.
- Error behavior stays JSON-only and consistent with existing bridge patterns.
- Unit tests for success and missing-parameter validation pass.
- Commands:
  - `pytest tests/unit/test_custom_bridge_gmail_actions.py -q`
- Thresholds:
  - Exit code `0`.
  - No new failures in targeted test run.

# Plan
1. Add `gmail_trash` and `gmail_delete` handlers using `GmailClient.request` with Gmail REST paths.
2. Register actions in bridge dispatch table.
3. Add focused unit tests for new handlers.
4. Run targeted tests and fix regressions.

# Commands
- `pytest tests/unit/test_custom_bridge_gmail_actions.py -q`

# Validation
- Verify both handlers return action/status/user_id/message_id.
- Verify missing `message_id` returns validation error.
- Result: `pytest tests/unit/test_custom_bridge_gmail_actions.py -q` -> `4 passed`.
- Result: `pytest tests/unit/test_custom_bridge_gmail_actions.py tests/unit/test_pa_gmail_delete_confirmation.py -q` -> `7 passed`.
- Result: `python -m py_compile scripts/e2e_pa_live.py` -> success.

# Recovery
- If tests fail on import/runtime assumptions, patch tests to mirror existing bridge style and re-run once.
- If route mismatch appears, align action names with canonical tool spec values.

# Notes
- Keep changes minimal and preserve existing API shape.
- Avoid introducing non-JSON responses or non-deterministic behavior.

# Progress
- Completed: Added `gmail_trash` and `gmail_delete` handlers in `backend/custom_bridge/__init__.py`.
- Completed: Registered both actions in `ACTION_HANDLERS` dispatch map.
- Completed: Added `tests/unit/test_custom_bridge_gmail_actions.py` with success and validation-path coverage.
- Completed: Added `audit_id` for side-effect Gmail operations (`send/trash/delete`).
- Completed: Extended PA normalization to support `delete_email` intent and explicit delete confirmation gate.
- Completed: Added `tests/unit/test_pa_gmail_delete_confirmation.py` for delete detection and confirmation behavior.
- Completed: Extended live E2E script with explicit destructive Gmail flow flags (`--run-destructive-gmail-e2e`, `--destructive-message-id`, `--allow-real-delete`).
- Completed: Updated status docs with March 10 delta (`REFACTOR_STATUS.md`, `docs/PATCH_2_STATUS.md`).