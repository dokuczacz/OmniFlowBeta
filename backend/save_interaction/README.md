# save_interaction

Logs user-assistant interactions to `users/{user_id}/interaction_logs.json`.

Endpoints:
- POST `/api/save_interaction`

Payload:
- `user_message` (required)
- `assistant_response` (required)
- `thread_id` (optional)
- `tool_calls` (optional)
- `metadata` (optional)

Notes:
- Requires `X-User-Id` and function key.
- Auto-creates log file and appends entries.
