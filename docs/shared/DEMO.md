# Demo notes (legacy Streamlit)

- Status: active (legacy)
- Audience: operator

The repo historically exposed a public Streamlit demo so reviewers could explore OmniFlow without local setup.

- URL: https://omniflowbeta-gjv5gjhezwbfg7pb7pucwe.streamlit.app/
- Backend target: the same Azure Functions deployment described in `docs/shared/DEPLOYMENT.md`

## Config to keep in sync

When you publish a new backend version, ensure the demo host points to the same backend:

- `BACKEND_BASE_URL` (or equivalent backend base URL in the Streamlit host)
- `FUNCTION_CODE_*` secrets (function keys)

## Note

Primary UI for Patch 2.0 is Next.js (`ui_next/`). Streamlit is maintained only as a LAB/demo surface.

