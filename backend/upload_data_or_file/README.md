# upload_data_or_file

Create or upload data/files under a user's namespace.

Endpoints:
- POST `/api/upload_data_or_file`

Payload (JSON):
- `file_name` (required)
- `file_content` (string or base64 for binary)
- `metadata` (optional)

Notes:
- Requires `X-User-Id` header and function key.
- Writes to `users/{user_id}/` paths.
