# Custom GPT / LLM Integration Guide

## Overview

OmniFlow Beta is designed to be integrated with Custom GPTs, LangChain agents, or any LLM-powered system that can make HTTP API calls. This document provides guidance on how to configure and use OmniFlow as a backend for your LLM applications.

---

## Required Environment Variables

To integrate OmniFlow with your Custom GPT or LLM system, ensure the following environment variables are configured:

### Core Configuration
- `AZURE_STORAGE_CONNECTION_STRING` - Azure Storage connection (or Azurite for local dev)
- `OPENAI_API_KEY` or `AZURE_OPENAI_API_KEY` - Your OpenAI/Azure OpenAI key
- `AZURE_OPENAI_ENDPOINT` (if using Azure OpenAI)
- `AZURE_OPENAI_DEPLOYMENT_NAME` (if using Azure OpenAI)

### Optional Configuration
- `OMNIFLOW_DEFAULT_CONTAINER` - Default blob container name (default: `omniflow-data`)
- `OMNIFLOW_MAX_BLOB_SIZE_MB` - Maximum blob size in MB (default: `10`)
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

See `.env.example` for a complete list of configuration options.

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
- `GET /api/custom_gpt_tools` - Return the catalog of callable functions along with their HTTP methods, URLs, and Azure function keys so your GPT can invoke them directly.

**Listing & Discovery**:
- `GET /api/list_blobs` - List all blobs for a user
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

## Streamlit Demo Integration Ideas

The included Streamlit frontend (`frontend/`) demonstrates basic integration. You can extend it to:

- **Multi-User Chat**: Allow multiple users to interact with their own data
- **File Upload UI**: Drag-and-drop file uploads to blob storage
- **Real-Time Logs**: Display audit logs and tool call history
- **Admin Dashboard**: View usage stats, user activity, and system health
- **Semantic Search UI**: Once vector search is implemented, add a search interface

Example Streamlit snippet:

```python
import streamlit as st
import requests

st.title("OmniFlow Beta Demo")

user_id = st.text_input("User ID")
blob_name = st.text_input("Blob Name")

if st.button("Read Blob"):
    response = requests.get(
        "http://localhost:7071/api/read_blob_file",
        headers={"X-User-Id": user_id},
        params={"blob_name": blob_name}
    )
    st.json(response.json())
```

---

## Low-Cost Demo Guidance

To minimize costs during development and demos:

1. **Use Azurite**: Local Azure Storage emulator (free)
2. **Limit OpenAI Calls**: Cache responses or use smaller models (e.g., `gpt-3.5-turbo`)
3. **Set Max Tokens**: Configure `max_tokens` to limit response length
4. **Local Testing**: Test all logic locally before deploying to Azure
5. **Free Tier**: Use Azure Functions Consumption Plan (first 1M executions free)

---

## Next Steps

1. **Configure Environment**: Copy `.env.example` to `.env` and fill in your keys
2. **Start Azurite**: Run `azurite` for local storage emulation
3. **Run Backend**: `cd backend && func start`
4. **Test Endpoints**: Use `curl` or Postman to test API calls
5. **Integrate with LLM**: Point your Custom GPT or LangChain agent to the API
6. **Deploy**: Once tested, deploy to Azure Functions for production use

For more details, see the main [README.md](README.md) and [docs/shared/README.md](docs/shared/README.md).

---

## Support & Feedback

For questions, issues, or feature requests, please open an issue on GitHub or contact the maintainer at dokuczacz@example.com.
