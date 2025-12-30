# OmniFlow Beta

OmniFlow Beta is a multi-user AI agent backend built on Azure Functions + Azure Blob Storage, with a Next.js UI.

## Current status (Patch 2.0)

- **WP1 (Responses + dual runtime)**: done (Responses is the default runtime).
- **WP7 (Semantic indexer, batch-first)**: available (queue → batch → semantic artifacts → index).
- **WP6 (context builder + cache)**: done (note: e2e cannot deterministically force `DEEP`).
- **WP2 (Next UI)**: done (Streamlit is legacy).
- **WP9 (reporting)**: available locally via strict JSONL writer under `docs/workflow/wp9_reporting/`.

## Live demo

- Streamlit (legacy LAB): https://omniflowbeta-gjv5gjhezwbfg7pb7pucwe.streamlit.app/

## Key features

- Per-user isolation via `X-User-Id` header (`users/{user_id}/...` in Blob).
- Deterministic tool orchestration via `POST /api/tool_call_handler` (Responses tool-loop).
- Storage tools: list/read/update/delete/upload + `read_many_blobs` (batch multi-read).
- Semantic pipeline (WP7) producing per-interaction semantic JSON artifacts + manifest index (consumed by WP6).

## Directory map

```
OmniFlowBeta/
  backend/      # Azure Functions (this folder is the function app root)
  ui_next/      # Next.js UI (primary)
  ai-chatbot/   # Next.js AI chat template (reference)
  frontend/     # Streamlit UI (legacy LAB console)
  docs/         # Architecture and handover docs
  scripts/      # Local helpers (ignored by default)
```

## Local run (recommended)

1) Backend deps: `pip install -r backend/requirements.txt`
2) Start Azurite (optional for local storage): `azurite`
3) Start Functions: `cd backend && func start`
4) Start Next UI: `cd ui_next && npm install && npm run dev`
5) (Optional) Start Streamlit UI: `cd frontend && streamlit run app.py`

## Docs

- Doc index: `docs/README.md`
- Patch 2.0 status: `docs/PATCH_2_STATUS.md`
- Semantics (WP7): `docs/WP7_Indexer_Batch.md`
- Context Builder (WP6): `docs/workflow/wp6_context_builder/README.md`
- Deployment: `docs/shared/DEPLOYMENT.md`
- Tool usage playbook: `FUNCTION_CALLS_PLAYBOOK.md`

## License

MIT.
