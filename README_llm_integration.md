# Custom GPT / LLM Integration Guide

## Overview

OmniFlow Beta is designed to be integrated with Custom GPTs, LangChain agents, or any LLM-powered system that can make HTTP API calls. This document provides guidance on how to configure and use OmniFlow as a backend for your LLM applications.

High-signal references (recommended to read first):

- Semantics (WP7): `docs/WP7_Indexer_Batch.md`
- Context Builder + cache (WP6): `docs/workflow/wp6_context_builder/README.md`
- Tool call patterns (strict): `FUNCTION_CALLS_PLAYBOOK.md`
- Doc index: `docs/README.md`

---

## Required Environment Variables

To integrate OmniFlow with your Custom GPT or LLM system, ensure the following environment variables are configured:

### Core Configuration
- `AZURE_STORAGE_CONNECTION_STRING` or `AzureWebJobsStorage` - Azure Storage connection (or Azurite for local dev)
- `AZURE_BLOB_CONTAINER_NAME` - Target container (default used by this repo: `agent-knowledge-base`)
- `OPENAI_API_KEY` - OpenAI key
- `LLM_RUNTIME` - `responses|assistants|auto` (recommended: `responses`)
- `OPENAI_PROMPT_ID` - Prompt ID configured in the OpenAI dashboard (Responses runtime)

### Optional Configuration
- `OPENAI_ASSISTANT_ID` - Assistant ID for legacy Threads/Assistants runtime
- `AZURE_PROXY_URL` - Proxy router endpoint (if you route tool calls through the proxy)
- `FUNCTION_URL_BASE` - Base URL used by proxy_router to construct endpoint URLs
- `FUNCTION_CODE_*` - Azure function keys for each endpoint (used by Custom GPT Actions)
- WP7 (Indexer): `OPENAI_INDEXER_PROMPT_ID`, `OPENAI_INDEXER_MODEL`, `WP7_INDEXER_MODE`, `WP7_INDEXER_USER_IDS`, `WP7_*` thresholds

See `.env.example` for a complete list of configuration options.

---

## WP6 AUTO Routing (FAST + optional DEEP escalation)

The Responses runtime supports a bounded "context routing" flow:

- `AUTO` (default): starts in `FAST` using a small semantic context snippet.
- `DEEP`: uses a Context Builder Prompt to generate a `context_pack` (JSON) based on candidate snippets.

### Agent signal for DEEP (FAST → DEEP)

In `AUTO` mode the first model call runs in `FAST`. The model can request one DEEP escalation by emitting a signal:

1) Preferred (first line JSON, single line):
```json
{"need_deep":false,"missing":[],"why":"","confidence":0.0,"deep_plan":[]}
```

2) Fallback token (if JSON is missing/unparseable):
```
__ROUTE_DEEP__
```

The backend will perform **at most one** DEEP escalation per user message. If DEEP is blocked (e.g., cooldown, insufficient inputs), the backend returns the FAST answer plus a short note.

### WP6 tuning env vars (local + Azure app settings)

- `WP6_DEFAULT_CONTEXT_MODE`: `AUTO|FAST|DEEP`
- `WP6_FAST_MAX_SOURCES`, `WP6_FAST_MAX_INPUT_TOKENS`, `WP6_FAST_MAX_RAW_BYTES`
- `WP6_DEEP_MAX_PACK_TOKENS`, `WP6_DEEP_MAX_CANDIDATE_SOURCES`
- `WP6_DEEP_MIN_SEMANTIC_SELECTED`, `WP6_DEEP_MIN_SEMANTIC_CANDIDATES`
- `WP6_DEEP_COOLDOWN_SECONDS`
- `OPENAI_CONTEXT_BUILDER_PROMPT_ID`

---

## Minimal Usage Pattern

### 1. Authentication
All API endpoints require user identification via the `X-User-Id` header:

```bash
curl -X POST http://localhost:7071/api/add_new_data \
  -H "Content-Type: application/json" \
  -H "X-User-Id: your_user_id_here" \
  -d '{"target_blob_name":"tasks.json","new_entry":{"id":"1","task":"Sample task"}}'
```

### 2. Key Endpoints for LLM Integration

**Tool Call Handler** (main orchestrator):
- `POST /api/tool_call_handler`
- Accepts tool calls in OpenAI function-calling format
- Routes to appropriate backend endpoints
- Returns structured responses

**Data Operations**:
- `POST /api/add_new_data` - Add new entries to JSON/structured data
- `GET /api/read_blob_file` - Read file contents
- `POST /api/upload_data_or_file` - Upload new files/data
- `PUT /api/update_data_entry` - Update existing entries
- `DELETE /api/remove_data_entry` - Remove entries

**Tool Discovery**:
- This repo includes an Actions OpenAPI file at `backend/custom_gpt_tools/actions_openapi.json`. If your deployment exposes a tool-catalog endpoint, keep it aligned with that schema.

**Listing & Discovery**:
- `GET /api/list_blobs` - List all blobs for a user
- `POST /api/read_many_blobs` - Read many blobs in one call (optional tail extraction for JSONL/text)
- `GET /api/get_current_time` - Get server timestamp

### 3. Example: Custom GPT Action

For a Custom GPT, you can define actions like (replace `servers` with your real endpoint):

```json
{
  "openapi": "3.0.0",
  "info": {
    "title": "OmniFlow Beta API",
    "version": "0.1.0"
  },
  "servers": [
    {
      "url": "https://agentbackendservice-dfcpcudzeah4b6ae.northeurope-01.azurewebsites.net/api"
    }
  ],
  "paths": {
    "/tool_call_handler": {
      "post": {
        "operationId": "toolCallHandler",
        "summary": "Execute tool calls",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "tool_name": {"type": "string"},
                  "tool_arguments": {"type": "object"}
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successful response"
          }
        }
      }
    }
  }
}
```

### Custom GPT Tool Catalog

Rather than hard-coding endpoints inside your assistant, call `/api/custom_gpt_tools` (with `X-User-Id`) to fetch a current catalog of allowed functions. Each tool entry still contains `name`, `description`, and `parameters`, plus:

- `function.methods`: HTTP verbs the endpoint supports (`GET`, `POST`, etc.).
- `function.url`: The full URL built from `FUNCTION_URL_BASE` so you know where to send the request.
- `function.code`: The Azure function key derived from `FUNCTION_CODE_*` environment variables (e.g., `FUNCTION_CODE_ADD_NEW_DATA`, `FUNCTION_CODE_READ_BLOB_FILE`).

With those fields the assistant can call any supported API directly:

```bash
curl "https://your-function-app.azurewebsites.net/api/list_blobs?code=<function_code>&user_id=alice"

curl -X POST "https://your-function-app.azurewebsites.net/api/add_new_data?code=<function_code>" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: alice" \
  -d '{"target_blob_name":"tasks.json","new_entry":{"id":"T001","task":"Sample task"}}'
```

Mirror the same env var names from `.env.example` or your Azure app settings so the catalog always reflects valid keys.

---

## Security & Privacy Notes

### User Isolation
- Every request **must** include a `X-User-Id` header or `user_id` parameter
- Data is isolated per user via namespacing (e.g., `user123/tasks.json`)
- No cross-user data access is permitted

### API Key Protection
- **Never** expose your OpenAI/Azure API keys in Custom GPT configurations
- Use environment variables or Azure Key Vault in production
- Implement rate limiting and monitoring for production deployments

### Audit Logging
- All tool calls are logged with full context (user, tool name, arguments, results)
- Logs include timestamps and can be used for compliance and debugging
- Review logs regularly for anomalous activity

---

## Audit Suggestions

1. **Review Logs Regularly**: Check interaction history via `/api/get_interaction_history`
2. **Monitor Usage**: Track API call frequency and patterns per user
3. **Validate Inputs**: OmniFlow validates user IDs and blob names—extend as needed
4. **Rate Limiting**: Consider implementing rate limits for production use
5. **Error Tracking**: Set up alerts for 4xx/5xx responses

---

## UI clients (deployment note)

- Product UI (Next.js): `ui_next/`
- AI chat template (reference): `ai-chatbot/`
- Legacy Streamlit LAB UI: `frontend/`
