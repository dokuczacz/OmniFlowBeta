# manage_files

User-scoped file management operations.

Endpoints:
- POST `/api/manage_files` with action: `list|rename|delete`
- Requires header `X-User-Id` and function key.

Notes:
- Operates under `users/{user_id}/` namespace.
- Listing returns only the current user's files.
