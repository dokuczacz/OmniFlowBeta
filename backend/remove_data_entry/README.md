# remove_data_entry

Delete an entry or file in the user's namespace.

Endpoints:
- POST `/api/remove_data_entry`

Payload:
- `file_name`
- `key_to_find` (optional)
- `value_to_match` (optional)
- If no key/value provided, deletes entire file.

Notes:
- Requires `X-User-Id` and function key.
- Affects `users/{user_id}/` paths only.
