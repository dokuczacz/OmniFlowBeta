# OmniFlow Beta

OmniFlow Beta is a multi-user AI agent backend built on Azure Functions + Azure Blob Storage, with a Streamlit LAB UI.

## Current status (Patch 2.0)

- **WP1 (Responses + dual runtime)**: done (Responses is the default runtime).
- **WP7 (Semantic indexer, batch-first)**: available (queue → batch → semantic artifacts → index).
- **WP6 (next)**: session restore + context builder (must be done before the new UI).
- **WP9 (reporting)**: available locally via strict JSONL writer under `docs/workflow/wp9_reporting/`.

## Live demo

- Streamlit: https://omniflowbeta-gjv5gjhezwbfg7pb7pucwe.streamlit.app/

## Key features

- Per-user isolation via `X-User-Id` header (`users/{user_id}/...` in Blob).
- Deterministic tool orchestration via `POST /api/tool_call_handler` (Responses tool-loop).
- Storage tools: list/read/update/delete/upload + `read_many_blobs` (batch multi-read).
- Optional semantic pipeline (WP7) producing per-interaction semantic JSON artifacts + manifest index.

## Directory map

```
OmniFlowBeta/
  backend/      # Azure Functions (this folder is the function app root)
  frontend/     # Streamlit UI (LAB console)
  docs/         # Architecture and handover docs
  scripts/      # Local helpers (ignored by default)
```

## Local run (recommended)

1) Backend deps: `pip install -r backend/requirements.txt`
2) Start Azurite (optional for local storage): `azurite`
3) Start Functions: `cd backend && func start`
4) Start Streamlit UI: `cd frontend && streamlit run app.py`

## Docs

- Handover / big plan: `docs/OmniFlow_Project_Summary_and_Next_Steps.md`
- Deployment: `docs/shared/DEPLOYMENT.md`
- Tool usage playbook: `FUNCTION_CALLS_PLAYBOOK.md`

## License

MIT.

