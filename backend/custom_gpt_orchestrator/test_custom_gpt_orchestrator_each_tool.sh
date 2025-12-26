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

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required env var: ${name}" >&2
    exit 1
  fi
}

call_tool() {
  local tool="$1"
  local params_json="$2"
  echo "Calling tool: ${tool}"
  curl -sS -X POST \
    -H "Content-Type: application/json" \
    -H "X-User-Id: ${USER_ID}" \
    -d "{\"tool\":\"${tool}\",\"params\":${params_json}}" \
    "${URL}" | python -m json.tool
}

call_tool "get_current_time" "{}"

require_env "TARGET_BLOB_NAME"
require_env "NEW_ENTRY_JSON"
call_tool "add_new_data" "{\"target_blob_name\":\"${TARGET_BLOB_NAME}\",\"new_entry\":${NEW_ENTRY_JSON}}"

require_env "TARGET_BLOB_NAME"
call_tool "get_filtered_data" "{\"target_blob_name\":\"${TARGET_BLOB_NAME}\"}"

require_env "MANAGE_OPERATION"
call_tool "manage_files" "{\"operation\":\"${MANAGE_OPERATION}\"}"

require_env "TARGET_BLOB_NAME"
require_env "FIND_KEY"
require_env "FIND_VALUE"
require_env "UPDATE_KEY"
require_env "UPDATE_VALUE"
call_tool "update_data_entry" "{\"target_blob_name\":\"${TARGET_BLOB_NAME}\",\"find_key\":\"${FIND_KEY}\",\"find_value\":\"${FIND_VALUE}\",\"update_key\":\"${UPDATE_KEY}\",\"update_value\":\"${UPDATE_VALUE}\"}"

require_env "TARGET_BLOB_NAME"
require_env "KEY_TO_FIND"
require_env "VALUE_TO_FIND"
call_tool "remove_data_entry" "{\"target_blob_name\":\"${TARGET_BLOB_NAME}\",\"key_to_find\":\"${KEY_TO_FIND}\",\"value_to_find\":\"${VALUE_TO_FIND}\"}"

require_env "TARGET_BLOB_NAME"
require_env "FILE_CONTENT"
call_tool "upload_data_or_file" "{\"target_blob_name\":\"${TARGET_BLOB_NAME}\",\"file_content\":\"${FILE_CONTENT}\"}"

call_tool "list_blobs" "{}"

require_env "READ_BLOB_FILE_NAME"
call_tool "read_blob_file" "{\"file_name\":\"${READ_BLOB_FILE_NAME}\"}"

require_env "USER_MESSAGE"
require_env "ASSISTANT_RESPONSE"
call_tool "save_interaction" "{\"user_message\":\"${USER_MESSAGE}\",\"assistant_response\":\"${ASSISTANT_RESPONSE}\"}"

call_tool "get_interaction_history" "{}"
