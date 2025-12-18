CHANGES — tool_call_handler updates

Files modified:
- backend/tool_call_handler/__init__.py
  - Added env-gated debug logging and `_redact_sensitive()`.
  - Introduced `_make_response()` that returns a real `func.HttpResponse` when the Azure Functions runtime is present, otherwise returns a tuple for local tests.
  - Audited `main()` and ensured all return paths produce supported outputs for the Functions worker.
  - Hardened `execute_tool_call()` proxy GET/POST branches with input validation, exception handling, and normalized JSON responses.
  - Removed temporary debug prints added during local debugging.

Files added to support testing and QA:
- backend/tooling/tmp_invoke_tool_call_handler.py (used earlier for local debugging)
- backend/tests/test_tool_call_handler.py (pytest scaffold)
- backend/TESTER_INSTRUCTIONS.md (how to run repro and tests)
- IMPLEMENTER_AGENT.md (restored implementer plan file)

Summary:
- Fixed a worker conversion error by ensuring the function returns a supported HTTP response object under the Functions runtime.
- Hardened proxy interactions and direct save/get flows to return clear errors on misconfiguration or request failures.

Next suggested steps:
- Tester: run `pytest` and the repro as described in `backend/TESTER_INSTRUCTIONS.md`.
- After QA, review for commit and push to remote.
