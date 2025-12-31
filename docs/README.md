# OmniFlowBeta Documentation Index

This folder is the **source of truth** for project documentation.

If you are updating docs, follow `docs/shared/DOCS_STANDARD.md`.

## Quick map (start here)

- Patch 2.0 status (source of truth): `docs/PATCH_2_STATUS.md`
- Legacy handover (historical): `docs/OmniFlow_Project_Summary_and_Next_Steps.md`
- WP6 Context Builder (schema + contract): `docs/workflow/wp6_context_builder/README.md`
- WP7 Semantic Indexer (batch-first): `docs/WP7_Indexer_Batch.md`
- Deployment (backend + UIs): `docs/shared/DEPLOYMENT.md`
- User isolation / namespacing: `docs/shared/USER_MANAGEMENT.md`
- Agent↔agent exchange contract (JSONL): `docs/shared/AGENT_EXCHANGE_TABLE.template.jsonl.md`
- WP9 reporting (local JSONL writer): `docs/workflow/wp9_reporting/README.md`

## Environment templates

- Root env template: `.env.example`
- Azure Functions local template: `backend/local.settings.template.json`
- Next UI env template: `ui_next/.env.example`
- AI chat template env: `ai-chatbot/.env.example` and `ai-chatbot/.env.local.example`
- Streamlit (legacy) secrets template: `frontend/.streamlit/secrets.toml.example`

## UI note (Patch 2.0)

- Product UI (Next.js): `ui_next/` (primary)
- AI chat template (reference): `ai-chatbot/`
- Legacy LAB UI (Streamlit): `frontend/`
