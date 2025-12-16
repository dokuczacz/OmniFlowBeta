# Custom GPT / LLM Integration Guide

## Overview

OmniFlow Beta provides a REST API designed for seamless integration with AI assistants, including Custom GPTs, Claude Projects, and other LLM-powered applications. All endpoints enforce user isolation and provide comprehensive audit logging.

## Quick Start for Custom GPTs

### 1. Configure Your Custom GPT Actions

Use the following OpenAPI schema to configure your Custom GPT actions:

**Base URL**: `https://your-deployment.azurewebsites.net/api` (replace with your Azure Functions URL)

**Authentication**: None required for basic operations (user context via headers/params)

### 2. Key Endpoints for Custom GPTs

#### Core Data Operations
- **POST /add_new_data** - Add new entries to JSON files
- **POST /read_blob_file** - Read file contents
- **POST /update_data_entry** - Update existing entries
- **POST /remove_data_entry** - Remove entries
- **POST /upload_data_or_file** - Upload or overwrite files
- **GET /list_blobs** - List user files

#### AI-Powered Tool Routing
- **POST /tool_call_handler** - Natural language tool routing (recommended)

### 3. User Context

All endpoints require a user context for isolation. Provide via:
- **Header**: `X-User-Id: your_user_id`
- **Query param**: `?user_id=your_user_id`
- **Body param**: `"user_id": "your_user_id"`

For Custom GPTs, you can hardcode a user ID per GPT instance or pass it dynamically.

### 4. Example: Configure "Add Task" Action

```json
{
  "openapi": "3.0.0",
  "info": {
    "title": "OmniFlow Beta API",
    "version": "0.1.0"
  },
  "servers": [
    {
      "url": "https://your-deployment.azurewebsites.net/api"
    }
  ],
  "paths": {
    "/add_new_data": {
      "post": {
        "operationId": "addNewData",
        "summary": "Add a new data entry to a JSON file",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "target_blob_name": {
                    "type": "string",
                    "description": "Name of the JSON file (e.g., tasks.json)"
                  },
                  "new_entry": {
                    "type": "object",
                    "description": "The data entry to add"
                  },
                  "user_id": {
                    "type": "string",
                    "description": "User identifier for data isolation"
                  }
                },
                "required": ["target_blob_name", "new_entry"]
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Entry added successfully"
          }
        }
      }
    },
    "/tool_call_handler": {
      "post": {
        "operationId": "toolCallHandler",
        "summary": "Natural language tool routing with AI",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "message": {
                    "type": "string",
                    "description": "Natural language request"
                  },
                  "user_id": {
                    "type": "string",
                    "description": "User identifier"
                  },
                  "thread_id": {
                    "type": "string",
                    "description": "Optional conversation thread ID"
                  }
                },
                "required": ["message"]
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Tool executed successfully"
          }
        }
      }
    }
  }
}
```

### 5. Using Tool Call Handler (Recommended)

The `tool_call_handler` endpoint uses OpenAI's function calling to route natural language requests to the appropriate backend tools automatically.

**Example request:**
```json
{
  "message": "Add a task: Review pull requests, due tomorrow",
  "user_id": "alice_123",
  "thread_id": "conv_001"
}
```

**Example response:**
```json
{
  "status": "success",
  "result": "Task added successfully",
  "tools_called": ["add_new_data"],
  "interaction_id": "int_abc123"
}
```

## Integration with Other LLM Platforms

### Claude Projects / Artifacts

Configure Claude to use OmniFlow Beta API by providing:
1. API endpoint URLs
2. Request/response formats
3. Example curl commands

**Example curl for Claude:**
```bash
curl -X POST https://your-deployment.azurewebsites.net/api/add_new_data \
  -H "Content-Type: application/json" \
  -H "X-User-Id: claude_user_001" \
  -d '{
    "target_blob_name": "notes.json",
    "new_entry": {"id": "1", "text": "Meeting notes"}
  }'
```

### LangChain Integration

```python
from langchain.tools import Tool
import requests

def omniflow_add_data(target_blob_name: str, new_entry: dict, user_id: str):
    """Add data to OmniFlow Beta"""
    response = requests.post(
        "https://your-deployment.azurewebsites.net/api/add_new_data",
        headers={"X-User-Id": user_id},
        json={"target_blob_name": target_blob_name, "new_entry": new_entry}
    )
    return response.json()

omniflow_tool = Tool(
    name="OmniFlow_AddData",
    func=omniflow_add_data,
    description="Add new data entries to user storage"
)
```

### Zapier / Make.com Integration

1. Use **Webhooks** module
2. Set method to **POST**
3. Add headers: `Content-Type: application/json`, `X-User-Id: your_user_id`
4. Configure JSON body based on endpoint requirements

## Authentication & Security

### Current Implementation
- User isolation via `user_id` parameter/header
- No API key required for basic operations
- All data scoped to user namespace

### Production Recommendations
1. **Add API Key Authentication**: Implement Azure API Management or custom middleware
2. **Use Azure AD**: Integrate with Azure Active Directory for enterprise SSO
3. **Rate Limiting**: Configure throttling via Azure Functions settings
4. **IP Whitelisting**: Restrict access to known IP ranges
5. **HTTPS Only**: Enforce HTTPS in production (automatic with Azure Functions)

## Advanced Features

### Thread-Based Conversations
Use `thread_id` parameter to maintain conversation context:
```json
{
  "message": "What tasks are due today?",
  "user_id": "alice_123",
  "thread_id": "conv_20241216_001"
}
```

### Interaction History
All tool calls are automatically logged with:
- User message
- Assistant response
- Tool calls and results
- Timestamps
- Thread ID

Query history via:
```bash
curl -X GET "https://your-deployment.azurewebsites.net/api/get_interaction_history?user_id=alice_123&limit=10"
```

### Multi-User Scenarios
Each Custom GPT or LLM instance can have its own `user_id` for complete data isolation:
- **Sales GPT**: `user_id=sales_team`
- **Support GPT**: `user_id=support_team`
- **Personal Assistant**: `user_id=alice_123`

## Testing Your Integration

### 1. Test with curl
```bash
# Add test data
curl -X POST http://localhost:7071/api/add_new_data \
  -H "Content-Type: application/json" \
  -H "X-User-Id: test_user" \
  -d '{"target_blob_name":"test.json","new_entry":{"id":"1","text":"Test"}}'

# Read it back
curl -X GET "http://localhost:7071/api/read_blob_file?file_name=test.json&user_id=test_user"
```

### 2. Test with Postman
Import the OpenAPI schema into Postman and test all endpoints.

### 3. Test with Custom GPT
Configure a test action and verify:
- User isolation works correctly
- Responses are formatted properly
- Errors are handled gracefully

## Troubleshooting

### Common Issues

**Issue**: "User ID is missing or empty"
- **Solution**: Ensure `X-User-Id` header or `user_id` param is provided

**Issue**: "File not found"
- **Solution**: Verify the file exists for this user via `/list_blobs`

**Issue**: "Invalid JSON"
- **Solution**: Ensure request body is valid JSON and `Content-Type` header is set

**Issue**: "500 Internal Server Error"
- **Solution**: Check Azure Functions logs via Azure Portal or `func logs`

## Deployment Guide

### Deploy to Azure

1. **Create Azure Function App**:
   ```bash
   az functionapp create --resource-group MyResourceGroup \
     --consumption-plan-type Y1 --runtime python --runtime-version 3.11 \
     --functions-version 4 --name omniflow-beta --storage-account mystorageaccount
   ```

2. **Deploy code**:
   ```bash
   cd backend
   func azure functionapp publish omniflow-beta
   ```

3. **Configure environment variables**:
   ```bash
   az functionapp config appsettings set --name omniflow-beta \
     --resource-group MyResourceGroup \
     --settings AzureWebJobsStorage="<connection_string>" OPENAI_API_KEY="<your_key>"
   ```

4. **Get your API URL**:
   ```bash
   az functionapp show --name omniflow-beta --resource-group MyResourceGroup \
     --query defaultHostName --output tsv
   ```
   Your API will be at: `https://<hostname>/api/<endpoint>`

### Local Development

1. Install dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. Start Azurite:
   ```bash
   azurite
   ```

3. Start Azure Functions:
   ```bash
   func start
   ```

4. API available at: `http://localhost:7071/api/<endpoint>`

## Support & Contributing

- **Issues**: https://github.com/dokuczacz/OmniFlowBeta/issues
- **Discussions**: https://github.com/dokuczacz/OmniFlowBeta/discussions
- **Contributing**: See CONTRIBUTING.md

## License

Apache-2.0 - See LICENSE file for details
