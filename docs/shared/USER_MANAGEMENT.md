# User Management System Documentation

## Overview

This backend now supports **multi-user isolation** while maintaining a single container. Each user's data is automatically namespaced under their unique ID, preventing data leakage between users.

---

## Architecture

### User Namespace Structure

All user data is stored with a consistent prefix pattern:

```
users/{user_id}/{file_name}
```

**Examples:**
- `users/alice_123/tasks.json` - Alice's task list
- `users/bob_456/ideas.json` - Bob's ideas
- `users/default/knowledge.json` - Default user data

### Key Components

#### 1. **`shared/config.py`** - Configuration Management
- Centralized Azure configuration
- `AzureConfig` class with environment variables
- `UserNamespace` class for namespace operations

#### 2. **`shared/user_manager.py`** - User Authentication & Validation
- `UserValidator` - Extract and validate user IDs from requests
- `UserAuthorization` - Check user access rights
- `extract_user_id()` - Convenience function

#### 3. **`shared/azure_client.py`** - Azure Blob Client Factory
- Singleton pattern for connection management
- `AzureBlobClient` - Factory methods for blob operations
- Automatic user namespace injection
- Methods:
  - `get_blob_client(blob_name, user_id)` - Get user-scoped blob client
  - `list_user_blobs(user_id, prefix)` - List user's blobs only
  - `blob_exists(blob_name, user_id)` - Check blob existence

---

## User ID Extraction

User IDs are extracted from HTTP requests in this order of priority:

1. **HTTP Header**: `X-User-Id`
2. **Query Parameter**: `user_id` or `userId`
3. **Request Body (JSON)**: `user_id` or `userId`
4. **Default**: `"default"` if no user ID provided

### Examples

#### Example 1: Header-based (Recommended)
```bash
curl -X POST https://your-function.azurewebsites.net/api/add_new_data \
  -H "Content-Type: application/json" \
  -H "X-User-Id: alice_123" \
  -d '{
    "target_blob_name": "tasks.json",
    "new_entry": {"id": "T001", "content": "Buy milk"}
  }'
```

#### Example 2: Query parameter
```bash
curl -X GET "https://your-function.azurewebsites.net/api/read_blob_file?file_name=tasks.json&user_id=alice_123"
```

#### Example 3: Request body
```bash
curl -X POST https://your-function.azurewebsites.net/api/add_new_data \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice_123",
    "target_blob_name": "tasks.json",
    "new_entry": {"id": "T001", "content": "Buy milk"}
  }'
```

### User ID Validation

Valid user IDs must:
- Be 3-64 characters long
- Contain only alphanumeric characters, underscores, hyphens, or dots
- Examples: `alice_123`, `user-456`, `team.project`

---

## Function Updates

All updated functions now support user isolation:

### 1. **read_blob_file** - Read user's file
```json
{
  "file_name": "tasks.json",
  "user_id": "alice_123" (optional - from header/param/body)
}
```

**Response:**
```json
{
  "status": "success",
  "data": [...],
  "user_id": "alice_123"
}
```

### 2. **list_blobs** - List user's files
```bash
GET /api/list_blobs?prefix=task&user_id=alice_123
```

**Response:**
```json
{
  "user_id": "alice_123",
  "blobs": ["tasks.json", "tasks_archive.json"],
  "count": 2
}
```

### 3. **add_new_data** - Add entry to user's file
```json
{
  "target_blob_name": "tasks.json",
  "new_entry": {"id": "T001", "content": "Buy milk"},
  "user_id": "alice_123" (optional)
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Entry successfully added to 'tasks.json'",
  "entry_count": 5,
  "user_id": "alice_123"
}
```

### 4. **get_filtered_data** - Query user's data
```json
{
  "target_blob_name": "tasks.json",
  "key": "status",
  "value": "open",
  "user_id": "alice_123" (optional)
}
```

**Response:**
```json
{
  "status": "success",
  "user_id": "alice_123",
  "file": "tasks.json",
  "filter": {"key": "status", "value": "open"},
  "data": [...filtered items...],
  "count": 3,
  "total": 7
}
```

---

## Security Considerations

### Data Isolation
- Each user can only access their own namespaced data
- The system **prevents** accessing other users' files by design
- User ID validation ensures proper namespace boundaries

### Future Enhancements
- **Authentication tokens** - Replace simple user ID with JWT/OAuth2
- **Admin bypass** - Currently placeholder `X-Admin-Token: admin`
- **Audit logging** - Track all data access per user
- **Rate limiting** - Prevent abuse per user/IP

### Current Limitations
- **No persistent authentication** - User ID must be provided with each request
- **No encryption per user** - All data encrypted at rest by Azure
- **Basic authorization** - Only user owns their data (no role-based access)

---

## Migration Guide

### For Existing Integrations

If you have external systems calling this backend:

1. **Add user ID header** to all requests:
   ```
   X-User-Id: your_unique_user_id
   ```

2. **No other changes needed** - Functions remain backward compatible
   - If no user ID provided, defaults to `"default"` namespace
   - Existing `"default"` user data continues to work

3. **Separate users' data** by providing different `X-User-Id` values

---

## Environment Configuration

The system uses these environment variables (already set in `local.settings.json`):

```json
{
  "AZURE_STORAGE_CONNECTION_STRING": "...",
  "AZURE_BLOB_CONTAINER_NAME": "agent-knowledge-base",
  "OPENAI_API_KEY": "...",
  "PROXY_URL": "..."
}
```

No additional configuration needed for user isolation - it's automatic.

---

## Testing Multi-User Scenarios

### Test Case 1: Data Isolation
```bash
# Add data for user alice
curl -X POST https://your-function.azurewebsites.net/api/add_new_data \
  -H "X-User-Id: alice_123" \
  -H "Content-Type: application/json" \
  -d '{"target_blob_name": "tasks.json", "new_entry": {"id": "T1"}}'

# List data for user alice
curl -X GET "https://your-function.azurewebsites.net/api/list_blobs?user_id=alice_123"
# Output: ["users/alice_123/tasks.json"]

# List data for user bob
curl -X GET "https://your-function.azurewebsites.net/api/list_blobs?user_id=bob_456"
# Output: [] (empty - bob has no data yet)
```

### Test Case 2: Data Access
```bash
# Alice reads her tasks
curl -X GET "https://your-function.azurewebsites.net/api/read_blob_file?file_name=tasks.json&user_id=alice_123"
# Returns: Alice's tasks

# Bob tries to read alice's tasks (will fail)
curl -X GET "https://your-function.azurewebsites.net/api/read_blob_file?file_name=tasks.json&user_id=bob_456"
# Returns: 404 File not found (bob's namespace has no tasks.json)
```

---

## File Structure

```
shared/
├── __init__.py              # Package marker
├── config.py                # Configuration & namespace management
├── user_manager.py          # User authentication & validation
└── azure_client.py          # Azure Blob client factory

read_blob_file/
├── __init__.py              # Updated with user isolation
└── function.json

list_blobs/
├── __init__.py              # Updated with user isolation
└── function.json

add_new_data/
├── __init__.py              # Updated with user isolation
└── function.json

get_filtered_data/
├── __init__.py              # Updated with user isolation
└── function.json

...other functions...
```

---

## Next Steps

1. **Update remaining functions** - `update_data_entry`, `remove_data_entry`, `upload_data_or_file`, `manage_files`
   - Apply same pattern: import shared utilities, extract user ID, pass to Azure client

2. **Add authentication layer** - Replace simple user ID with secure tokens
   - Implement proper JWT validation
   - Secure admin operations

3. **Add audit logging** - Track all data access
   - Log user ID, action, timestamp, success/failure
   - Store in separate audit table

4. **Implement rate limiting** - Prevent abuse
   - Limit requests per user per minute
   - Track by user ID + IP address

5. **Add data encryption per user** (optional)
   - Encrypt blobs with per-user keys
   - Requires key management system
