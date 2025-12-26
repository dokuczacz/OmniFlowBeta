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

payload=$(python - <<'PY'
import json

payload = {
    "tool": "get_filtered_data",
    "params": {}
}
print(json.dumps(payload))
PY
)

echo "Calling tool with missing params (expect failure)"
status=$(curl -sS -o /tmp/custom_gpt_orchestrator_wrong_params.json -w "%{http_code}" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-User-Id: ${USER_ID}" \
  -d "${payload}" \
  "${URL}")

cat /tmp/custom_gpt_orchestrator_wrong_params.json | python -m json.tool

if [[ "${status}" -lt 400 ]]; then
  echo "Expected failure but got status ${status}" >&2
  exit 1
fi

echo "Received expected failure status ${status}"
