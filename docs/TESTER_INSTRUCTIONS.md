Tester Instructions — `tool_call_handler` verification

1) Start the Functions host (in `backend`):

PowerShell commands:

```powershell
Set-Location -Path 'C:\AI memory\NewHope\OmniFlowBeta\backend'
$env:DEBUG_TOOL_CALL_HANDLER = 'true'
func start --verbose
```

2) Run the repro script (from repo root):

```powershell
python backend/tooling/check_tool_call_handler.py
```

Expect a JSON `status: success` response. If 500 occurs, capture `backend/logs/tool_call_handler_repro.log` and share with Implementer.

3) Run unit tests (in a separate terminal):

```powershell
Set-Location -Path 'C:\AI memory\NewHope\OmniFlowBeta\backend'
python -m pytest -q
```

4) Integration checks:
- Call `GET /api/get_interaction_history?limit=5` with header `X-User-Id: test_user`.
- Call repro POST to `/api/tool_call_handler` as above.

Files added to help QA:
- `backend/tests/test_tool_call_handler.py` — pytest scaffold covering key behaviors.
- `backend/TESTER_INSTRUCTIONS.md` — this file.
- `CHANGES.md` — short summary of code changes for reviewer.

If you need me to run tests or collect outputs, I can do that now.
