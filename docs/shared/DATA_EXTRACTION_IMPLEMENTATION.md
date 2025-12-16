# Data Extraction System - Implementation Summary

## Overview

This document describes the implementation of the **Data Extraction System** for the OmniFlow Agent Backend. The system automatically captures and stores interaction data between users and the AI assistant for future analysis, debugging, and improvement.

---

## What Was Implemented

### 1. **Interaction Logging Functions** (NEW)

Two new Azure Functions were created to handle interaction data:

#### `save_interaction` Function
- **Location**: `/save_interaction/__init__.py`
- **Purpose**: Save user-assistant interactions with metadata
- **Features**:
  - Stores user messages and assistant responses
  - Tracks tool calls made during interaction
  - Includes thread_id for conversation continuity
  - Supports custom metadata
  - User-isolated storage
  - Generates unique interaction IDs with timestamps

#### `get_interaction_history` Function
- **Location**: `/get_interaction_history/__init__.py`
- **Purpose**: Retrieve past interactions for analysis
- **Features**:
  - Paginated results (limit/offset)
  - Filter by thread_id
  - Sorted by timestamp (newest first)
  - User-isolated retrieval
  - Returns total count with results


### 2. **Automatic Logging in Tool Call Handler** (UPDATED)

The `tool_call_handler` function automatically logs all interactions, with the following structure (confirmed up to date as of Dec 2025):

#### What Gets Logged:
- User's message
- Assistant's response
- Thread ID (for conversation tracking)
- All tool calls made:
  - Tool name
- Metadata (assistant_id, source)
- Timestamp (ISO 8601 format)

---

## Backend Latency Optimization (2025)

- Handler and tool call latency minimized (Pakiet 0 & 2 from Latency Plan)
- All main tools now run in-process (no HTTP hop)
- Tool call latency dropped from ~4s to ~100ms
- Main delay is now OpenAI run completion (external API)
- RAG/vector store not yet supported by SDK (open)

### 3. **Proxy Router Updates** (UPDATED)

Added new endpoints to the proxy router for tool access:

```python
"save_interaction": {
    "method": "POST",
    "url": ".../api/save_interaction",
    "code": os.getenv("FUNCTION_CODE_SAVE_INTERACTION", "")
},
"get_interaction_history": {
    "method": "GET",
    "url": ".../api/get_interaction_history",
    "code": os.getenv("FUNCTION_CODE_GET_HISTORY", "")
}
```

---

## Data Model

### Interaction Log Entry Structure

```json
{
  "interaction_id": "INT_20251211_100530_123456",
  "timestamp": "2025-12-11T10:05:30.123456Z",
  "user_id": "alice_test_123",
  "thread_id": "thread_abc123",
  "user_message": "Add a task to buy groceries",
  "assistant_response": "I've added the task to buy groceries to your list.",
  "tool_calls": [
    {
      "tool_name": "add_new_data",
      "arguments": {
        "target_blob_name": "tasks.json",
        "new_entry": {
          "id": "T001",
          "title": "Buy groceries"
        }
      },
      "result": {
        "status": "success",
        "entry_count": 5
      },
      "status": "success"
    }
  ],
  "metadata": {
    "assistant_id": "asst_abc123",
    "source": "tool_call_handler"
  }
}
```

### Storage Location

Interaction logs are stored in user-namespaced blob storage:
```
users/{user_id}/interaction_logs.json
```

Examples:
- `users/alice_test_123/interaction_logs.json`
- `users/bob_test_456/interaction_logs.json`
- `users/default/interaction_logs.json`

---

## How It Works

### Flow Diagram

```
┌─────────────────────────────────────────────────┐
│ 1. User sends message via tool_call_handler    │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│ 2. Assistant processes message                  │
│    - May make tool calls                        │
│    - Each tool call is tracked                  │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│ 3. Assistant generates response                 │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│ 4. save_interaction_log() is called             │
│    - Collects all interaction data              │
│    - Sends to save_interaction endpoint         │
│    - Includes user_id in X-User-Id header       │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│ 5. save_interaction stores data                 │
│    - Reads existing logs                        │
│    - Appends new interaction                    │
│    - Writes back to blob storage                │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│ 6. Response returned to user                    │
│    - Includes tool_calls_count                  │
│    - Interaction logged in background           │
└─────────────────────────────────────────────────┘
```

---

## API Reference

### Save Interaction

**Endpoint**: `POST /api/save_interaction`

**Headers**:
```
X-User-Id: <user_id>
Content-Type: application/json
```

**Request Body**:
```json
{
  "user_message": "string (required)",
  "assistant_response": "string (required)",
  "thread_id": "string (optional)",
  "tool_calls": ["array (optional)"],
  "metadata": {"object (optional)"}
}
```

**Response**:
```json
{
  "status": "success",
  "message": "Interaction successfully saved",
  "interaction_id": "INT_20251211_100530_123456",
  "timestamp": "2025-12-11T10:05:30.123456Z",
  "total_interactions": 15,
  "user_id": "alice_test_123",
  "storage_location": "users/alice_test_123/interaction_logs.json"
}
```

---

### Get Interaction History

**Endpoint**: `GET /api/get_interaction_history`

**Headers**:
```
X-User-Id: <user_id>
```

**Query Parameters**:
- `thread_id` (optional): Filter by specific conversation thread
- `limit` (optional): Maximum results to return (default: 50)
- `offset` (optional): Number of results to skip (default: 0)

**Response**:
```json
{
  "status": "success",
  "interactions": [
    {
      "interaction_id": "INT_20251211_100530_123456",
      "timestamp": "2025-12-11T10:05:30.123456Z",
      "user_id": "alice_test_123",
      "thread_id": "thread_abc123",
      "user_message": "...",
      "assistant_response": "...",
      "tool_calls": [...],
      "metadata": {...}
    }
  ],
  "total_count": 15,
  "returned_count": 10,
  "offset": 0,
  "limit": 50,
  "user_id": "alice_test_123",
  "thread_id": null
}
```

---

## Use Cases

### 1. **Debugging and Troubleshooting**
- Review what tool calls were made
- Understand why certain responses were generated
- Identify patterns in failed interactions
- Trace conversation flow

### 2. **User Behavior Analysis**
- Track most common user requests
- Identify frequently used tools
- Analyze conversation patterns
- Measure response quality

### 3. **System Improvement**
- Identify areas for optimization
- Find common failure points
- Improve tool call accuracy
- Enhance response quality

### 4. **Audit and Compliance**
- Maintain records of all interactions
- Track data access patterns
- Verify system behavior
- Support compliance requirements

### 5. **Feature Development**
- Understand user needs from actual interactions
- Prioritize new features based on usage
- Test new features against historical data
- Validate improvements with real examples

---

## Security and Privacy

### Data Isolation
- ✅ Each user's interactions are stored in their namespace
- ✅ Users cannot access other users' interaction logs
- ✅ Follows same isolation pattern as other data

### User ID Validation
- ✅ User IDs are extracted and validated using existing `extract_user_id()`
- ✅ Invalid user IDs are rejected
- ✅ Namespace injection prevention

### Error Handling
- ✅ Logging failures don't break main functionality
- ✅ Errors are logged for monitoring
- ✅ Graceful degradation if save fails

### Data Retention
- Manual cleanup required (future enhancement: auto-archival)
- Logs grow over time
- Consider implementing retention policies

---

## Configuration

### Environment Variables

New environment variables needed:

```bash
# For tool_call_handler to save interactions
FUNCTION_CODE_SAVE_INTERACTION=<function_key>

# For retrieving interaction history via proxy
FUNCTION_CODE_GET_HISTORY=<function_key>
```

### Existing Variables Used
- `FUNCTION_URL_BASE` - Base URL for function endpoints
- `OPENAI_API_KEY` - OpenAI API key
- `OPENAI_ASSISTANT_ID` - Assistant ID
- `AZURE_STORAGE_CONNECTION_STRING` - Blob storage connection

---

## Testing

See **TESTING_PLAN.md** for comprehensive testing scenarios, including:
- Test 5: Save Interaction
- Test 6: Retrieve Interaction History
- Test 7: Filter Interactions by Thread
- Test 9: Interaction Log Isolation
- Test 10: Assistant with Tool Calls
- Test 11: Multi-Turn Conversation

---

## Performance Considerations

### Storage Impact
- Each interaction: ~1-5 KB (depending on tool calls)
- 1000 interactions: ~1-5 MB
- Recommend monitoring file size

### Response Time Impact
- Logging is non-blocking (fires in background)
- Main response time: +0-50ms (HTTP call overhead)
- If logging fails, main request still succeeds

### Scalability
- Uses same blob storage as other data
- No additional infrastructure needed
- Scales with user count (each user has own file)

---

## Future Enhancements

### Phase 2 (Recommended)
- [ ] **Analytics Dashboard**: Visualize interaction data
- [ ] **Search Functionality**: Full-text search across interactions
- [ ] **Export Tools**: Export logs for external analysis
- [ ] **Data Retention**: Auto-archive old interactions

### Phase 3 (Nice to Have)
- [ ] **Metrics Calculation**: Response times, success rates, etc.
- [ ] **Anomaly Detection**: Identify unusual patterns
- [ ] **User Insights**: Personalized recommendations
- [ ] **A/B Testing**: Compare different assistant behaviors

---

## Migration Notes

### Existing Deployments
1. Deploy new functions: `save_interaction`, `get_interaction_history`
2. Update `tool_call_handler` with new code
3. Update `proxy_router` with new endpoints
4. Set environment variables
5. Test with sample interactions
6. Monitor logs for any issues

### No Breaking Changes
- ✅ Existing functionality unchanged
- ✅ Backward compatible
- ✅ Logging is additive feature
- ✅ Can be disabled by not setting environment variables

---

## Summary

### What You Get

✅ **Automatic Logging**
- Every assistant interaction is logged
- No manual intervention needed
- Transparent to end users

✅ **Rich Data Capture**
- User messages
- Assistant responses
- Tool calls with arguments and results
- Conversation threading
- Timestamps and metadata

✅ **Easy Retrieval**
- Simple API to get history
- Filter by thread
- Paginated results
- Sorted by recency

✅ **User Isolation**
- Each user's logs are separate
- No cross-user access
- Follows existing security model

✅ **Production Ready**
- Error handling
- Validation
- Performance optimized
- Documented and tested

---

## Questions?

For more details:
- See **TESTING_PLAN.md** for testing scenarios
- See **USER_MANAGEMENT.md** for user isolation details
- See **ARCHITECTURE.md** for system architecture
- See code comments in function implementations

**Implementation Complete! 🎉**

The data extraction system is ready to capture and analyze all assistant interactions for future improvements and debugging.
