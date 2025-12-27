# OmniFlow PA - Shiny UI (WP2)

This is the next-gen UI (Shiny for Python) for OmniFlow PA.

## Local run

1) Install deps:

```bash
pip install -r ui_shiny/requirements.txt
```

2) Set env vars:

- `BACKEND_URL` (tool_call_handler endpoint), e.g.:
  - local: `http://localhost:7071/api/tool_call_handler`
  - prod: `https://<your-app>.azurewebsites.net/api/tool_call_handler?code=<FUNCTION_KEY>`
- `UI_USERS_JSON` (per-user password map, see below)

3) Run:

```bash
python -m shiny run --reload ui_shiny/app.py
```

## UI_USERS_JSON

`UI_USERS_JSON` is a JSON object mapping `user_id` -> password hash string.

Format:

`pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>`

Example:

```json
{
  "MarioBros": "pbkdf2_sha256$260000$<salt_b64>$<hash_b64>"
}
```

Generate hashes:

```bash
python ui_shiny/hash_password.py --user MarioBros --password "your_password"
```

