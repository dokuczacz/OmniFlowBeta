# Deploying OmniFlow Beta

This document captures the steps, env vars, and sanity checks to publish the version currently in GitHub to Azure and keep the Streamlit demo in sync.

## Environment configuration

- Copy `.env.example` to `.env.local` (or another ignored filename) and fill in the required secrets before running locally or deploying. The template lists every `OPENAI_*`, `FUNCTION_CODE_*`, and debug flag the handler reads.
- When deploying to Azure, set the same key/value pairs in the Function App Configuration blade and in the Azure Static Web App/Streamlit deployment (or pass them via deployment scripts).
- Keep function codes secret. Rotate them through the Azure Portal and update `FUNCTION_CODE_*` values on the target environment before publishing.

## Publishing the backend

1. Authenticate with the Azure CLI and select your subscription.
2. Build and test locally: `pip install -r requirements.txt`, `func start`, and run the smoke tests (e.g. `python -m pytest backend/tool_call_handler/test_*.py`).
   - For a one-shot local runner (spawns separate PowerShell windows for Azurite, Functions, and Streamlit): `powershell -ExecutionPolicy Bypass -File scripts/run_local.ps1`
3. Publish your function app:
   ```bash
   func azure functionapp publish <YOUR_FUNCTION_APP_NAME> --python
   ```
   The CLI will push the fresh source and restart the app. Use `--publish-local-settings` to upload `.env.local` values when prompted.
4. Verify the deployed endpoints (`/api/tool_call_handler`, `/api/add_new_data`, etc.) respond with `200` and honor the `X-User-Id` header.
5. If you rely on the Azure proxy router, keep `AZURE_PROXY_URL`/`FUNCTION_CODE_PROXY_ROUTER` in sync between the router and the Functions app.

## Connecting the Streamlit UI

- The public demo runs at `https://omniflowbeta-gjv5gjhezwbfg7pb7pucwe.streamlit.app/`. Keep the backend base URL (and any function codes) aligned with the production Function App when updating the UI.
- To redeploy the frontend, publish your Streamlit app via Streamlit Community Cloud or another host and update `BACKEND_BASE_URL` + `FUNCTION_CODE_ADD_NEW_DATA` under the app’s secrets. The demo automatically points to the current API when the variables match.

## Post-deploy checklist

1. Confirm `tool_call_handler` logs show the expected `OPENAI_ASSISTANT_ID` and calls proceed without missing tool resources.
2. Use the deployed demo link to exercise the UI and ensure user threads persist.
3. Run the `docs/workflow/reports/agent_report_submit.py` script to capture the deployment milestone (e.g. assign the new report a “Azure publish” summary).

Once the backend and UI are stable, update the GitHub README/demo section so the next visitor sees the latest working demo and instructions.
