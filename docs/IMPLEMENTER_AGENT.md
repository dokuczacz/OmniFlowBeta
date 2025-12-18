Implementer Agent Plan

Mode: IMPLEMENT

Purpose:
- Implement steps from the approved plan to make `tool_call_handler` deterministic and robust.

Scope:
- Make targeted code changes inside `backend/tool_call_handler/__init__.py` according to the plan.
- Add env-gated debug logging and redaction for safe troubleshooting.
- Ensure every execution path returns a type supported by the Azure Functions Python worker.
- Harden proxy POST path and direct save/get flows, returning clear 4xx/5xx JSON errors on invalid inputs.
- Add unit and integration tests in `backend/tests` for the handler's key behaviors.
- Remove temporary debug prints and finalize commit.

Constraints:
- Do not change overall architecture or function bindings.
- Avoid refactoring unrelated modules.
- Do not modify authentication or storage namespaces without Orchestrator approval.

Steps:
1. Add env-gated debug logging and a `_redact_sensitive()` helper.
2. Reproduce the original failure locally and capture host logs.
3. Audit `main()` to ensure all return paths produce either a `func.HttpResponse` or a (body, status, headers) tuple accepted by the worker.
4. Patch problematic return paths and add a runtime-aware `_make_response()` helper.
5. Harden proxy POST path: ensure known GET-style endpoints are called with GET; validate inputs; marshal responses to JSON.
6. Harden `save_interaction` and `get_interaction_history` direct flows: enforce `user_id` and return clear errors.
7. Add unit tests covering:
   - Invalid JSON payload
   - Missing env config
   - Direct save/get flows
   - Proxy POST path with mocked `requests`
8. Run repro against local Functions host, capture logs, and iterate until stable.
9. Remove temporary debug prints and prepare commit.

Output (on completion):
- List of changed files.
- Per-file change summary.
- Test run output (local repro + unit tests).
- Whether implementation succeeded.

If any STOP condition in Implementer rules is hit, escalate to Orchestrator.
