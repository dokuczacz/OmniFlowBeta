# OmniFlow Beta

OmniFlow Beta is a multi-user AI orchestration backend on Azure Functions + Azure Blob Storage.

This repository exposes a quasi-MCP pattern: one deterministic orchestration endpoint with tool registry, validation, and structured responses.

## Test status

This project is currently in test/beta mode.

Test model (Custom GPT):

- [OmniFlow Personal Assistance (test)](https://chatgpt.com/g/g-69b01cec119481919adf992756bcde53-omniflow-personal-assistance)

## What you can connect

- `POST /api/tool_call_handler` - primary orchestration endpoint
- `POST /api/read_many_blobs` - batch blob reads
- `POST /api/save_interaction` - interaction log input for semantic processing

For full integration details, see:

- `docs/shared/MCP_AND_QUASI_MCP.md`

## Why quasi-MCP

- Single endpoint orchestration instead of one endpoint per tool
- Registry-driven tool specs and argument normalization
- Structured JSON errors and deterministic execution paths
- Multi-user isolation via `X-User-Id` and namespaced storage

## Current project layout

- `backend/` - Azure Functions backend (active in this repo)
- `ai-chatbot/` - Next.js chat frontend
- `frontend/` - Streamlit lab frontend (legacy/testing)
- `docs/` - source-of-truth documentation
- `tests/` - unit and e2e tests

## Quick start

1. Install backend dependencies: `pip install -r backend/requirements.txt`
2. Start Azurite: `azurite`
3. Run functions locally: `cd backend && func start`

Optional frontend runs:

- Next.js app: `cd ai-chatbot && pnpm install && pnpm dev`
- Streamlit lab UI: `cd frontend && streamlit run app.py`

## Key docs

- Docs index: `docs/README.md`
- Quasi-MCP guide: `docs/shared/MCP_AND_QUASI_MCP.md`
- Deployment: `docs/shared/DEPLOYMENT.md`
- Tool call playbook: `FUNCTION_CALLS_PLAYBOOK.md`
- Privacy policy: `docs/shared/PRIVACY_POLICY.md`
- Changelog: `CHANGELOG.md`

## Limitations

- WP6 DEEP path is not deterministically forceable end-to-end in all scenarios.
- Streamlit frontend is maintained as legacy/lab tooling.

## License

MIT
