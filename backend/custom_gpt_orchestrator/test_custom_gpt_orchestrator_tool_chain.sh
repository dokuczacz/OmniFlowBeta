#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:7071}"
ENDPOINT="/api/custom_gpt_orchestrator"
USER_ID="${USER_ID:-default}"

if [[ -n "${FUNCTION_CODE_CUSTOM_GPT_ORCHESTRATOR:-}" ]]; then
  URL="${BASE_URL}${ENDPOINT}?code=${FUNCTION_CODE_CUSTOM_GPT_ORCHESTRATOR}"
else
  URL="${BASE_URL}${ENDPOINT}"
fi

payload_two=$(python - <<'PY'
import json

payload = {
    "tool_chain": [
        {"tool": "list_blobs", "params": {}},
        {"tool": "read_blob_file", "params": {"file_name": "$prev[0].blobs[0]"}},
    ]
}
print(json.dumps(payload))
PY
)

echo "Calling tool_chain (2 steps)"
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "X-User-Id: ${USER_ID}" \
  -d "${payload_two}" \
  "${URL}" | python -m json.tool

payload_three=$(python - <<'PY'
import json

payload = {
    "tool_chain": [
        {"tool": "list_blobs", "params": {}},
        {"tool": "read_blob_file", "params": {"file_name": "$prev[0].blobs[0]"}},
        {"tool": "save_interaction", "params": {"user_message": "Loaded file", "assistant_response": "$prev[1]"}},
    ]
}
print(json.dumps(payload))
PY
)

echo "Calling tool_chain (3 steps)"
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "X-User-Id: ${USER_ID}" \
  -d "${payload_three}" \
  "${URL}" | python -m json.tool
