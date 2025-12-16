# update_data_entry

Update a JSON entry in a user file.

Endpoints:
- POST `/api/update_data_entry`

Payload:
- `file_name`
- `find_key`
- `find_value`
- `update_key`
- `update_value`

Notes:
- Requires `X-User-Id` and function key.
- Operates within `users/{user_id}/`.
