# Live Streamlit Demo

The current `main` branch is wired to a public Streamlit experience so reviewers can explore OmniFlow Beta without cloning or running azurite.

- **URL:** https://omniflowbeta-gjv5gjhezwbfg7pb7pucwe.streamlit.app/
- **Backend target:** the same Azure Functions deployment described in `docs/shared/DEPLOYMENT.md`.
- **Env vars:** ensure `BACKEND_BASE_URL` + `FUNCTION_CODE_ADD_NEW_DATA` (and other `FUNCTION_CODE_*` values) in the demo host match whatever you just pushed to Azure.

When you publish a new version, update this document (or rerun `docs/workflow/reports/agent_report_submit.py` with a “demo redeploy” summary) so visitors always see the active demo link.
