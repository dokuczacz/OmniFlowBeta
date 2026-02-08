# Dashboard vs Inline Tools Checklist (OmniFlowBeta)

## Goal
Keep Responses runtime deterministic and avoid drift between:
- OpenAI Dashboard prompt/tools
- `AGENT_FUNCTIONS_CATALOG.json` inline function schemas
- backend runtime flags in `tool_call_handler`

## Current baseline
- Runtime: `responses`
- Tool source default: `inline` (`OPENAI_RESPONSES_TOOL_SOURCE=inline`)
- Stateless default: `WP6_RESPONSES_STATELESS=true`

## Release checklist
1. Confirm runtime flags in backend:
- `WP6_RESPONSES_STATELESS=true`
- `OPENAI_RESPONSES_TOOL_SOURCE` is one of: `inline|dashboard|both`
- For production stability now: keep `inline`.

2. Confirm inline tool schema integrity:
- Source: `AGENT_FUNCTIONS_CATALOG.json` -> `openai_function_schemas`.
- Every object schema has:
  - `"type": "object"`
  - explicit `"properties"`
  - explicit `"required"` containing all property keys
  - `"additionalProperties": false`

3. Confirm Dashboard Prompt content policy:
- Prompt does not include full manifest/contracts payloads.
- Prompt does not redefine tool contract differently than inline catalog.
- Prompt keeps role: assistant text generation, backend owns orchestration/state.

4. Decide single source for tool declarations per environment:
- `inline` (recommended): tools sent from backend each call.
- `dashboard`: tools managed in OpenAI UI only.
- `both`: temporary migration only, not long-term.

5. Validate with focused smoke:
- Ask: "dawno mnie nie było, co tam mamy z aktualności?"
- Expected behavior:
  - assistant first checks user data via tools
  - no manifest dump
  - no `Invalid schema` / `invalid_function_parameters` in logs.

## Operator commands
```powershell
cd C:\AI memory\NewHope\OmniFlowBeta

# 1) Runtime flags and tool-source check in latest func log
rg -n "WP6_RESPONSES_STATELESS|tool_source|Invalid schema|invalid_function_parameters" tmp/logs/func_*.log

# 2) Confirm task-first tool calls happened
rg -n "Dispatching tool: list_blobs|Dispatching tool: read_blob_file|Dispatching tool: read_many_blobs" tmp/logs/func_*.log

# 3) Confirm no runtime schema/tool-dispatch errors
rg -n "Tool dispatch not available|Traceback|status\": \"500\"|invalid_function_parameters" tmp/logs/func_*.log
```

## Success signal
- Chat response is user-facing and task-first.
- Logs contain tool calls with `OK via registry dispatch`.
- No schema/tool-dispatch/runtime 500 errors.

