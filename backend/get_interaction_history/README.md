# get_interaction_history

Returns interaction history for a user.

Endpoints:
- GET `/api/get_interaction_history`

Query:
- `limit` (default 50, max 1000)
- `offset` (default 0)
- `thread_id` (optional)

Notes:
- Requires `X-User-Id` and function key.
- Reads from `users/{user_id}/interaction_logs.json`.
