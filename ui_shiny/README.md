# OmniFlow PA - Shiny UI (WP2)

This is the next-gen UI (Shiny for Python) for OmniFlow PA.

## Local run

1) Install deps:

```bash
pip install -r ui_shiny/requirements.txt
```

2) Set env vars:

- `BACKEND_URL` (optional override for tool_call_handler endpoint), e.g.:
  - local: `http://localhost:7071/api/tool_call_handler`
  - prod: `https://<your-app>.azurewebsites.net/api/tool_call_handler?code=<FUNCTION_KEY>`
- or use environment presets:
  - `BACKEND_URL_PROD` (recommended)
  - `BACKEND_URL_DEV` (optional)
  - `UI_ENV=prod|dev` (default: prod)
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

## Shiny Templates

This directory includes the official [Shiny for Python templates](https://github.com/posit-dev/py-shiny-templates) as a git submodule in `ui_shiny/py-shiny-templates/`.

The templates provide examples and starter code for various Shiny application patterns:
- Basic apps and dashboards
- Navigation patterns
- Database integration
- Gen AI applications
- And more

To initialize the submodule (if not already done):

```bash
git submodule update --init --recursive
```

Browse the templates in `ui_shiny/py-shiny-templates/` to find patterns and examples for your Shiny development.
