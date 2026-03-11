# OmniFlowBeta Documentation Index

This folder is the source of truth for OmniFlowBeta documentation.

If you update docs, follow `docs/shared/DOCS_STANDARD.md`.

## Start here

- Project landing: `README.md`
- Quasi-MCP integration guide: `docs/shared/MCP_AND_QUASI_MCP.md`
- Deployment guide: `docs/shared/DEPLOYMENT.md`
- Tool-call playbook: `FUNCTION_CALLS_PLAYBOOK.md`

## Beta modes

- Native UI beta (full Context Builder/features): `ai-chatbot/` + `backend/`
- Custom GPT beta (integration path): see `docs/shared/MCP_AND_QUASI_MCP.md`

## Core architecture docs

- Patch 2.0 status: `docs/PATCH_2_STATUS.md`
- WP6 context builder: `docs/workflow/wp6_context_builder/README.md`
- WP7 semantic indexer: `docs/WP7_Indexer_Batch.md`
- WP9 reporting writer: `docs/workflow/wp9_reporting/README.md`
- User isolation and namespacing: `docs/shared/USER_MANAGEMENT.md`

## Governance and shared references

- Documentation standard: `docs/shared/DOCS_STANDARD.md`
- Privacy policy: `docs/shared/PRIVACY_POLICY.md`
- Discussion templates: `docs/shared/GITHUB_DISCUSSIONS_TEMPLATES.md`

## Environment templates

- Root env template: `.env.example`
- Azure Functions local template: `backend/local.settings.template.json`
- AI chatbot env templates: `ai-chatbot/.env.example`, `ai-chatbot/.env.local.example`
- Streamlit secrets template: `frontend/.streamlit/secrets.toml.example`

## UI status

- Active Next.js app: `ai-chatbot/`
- Legacy/lab Streamlit app: `frontend/`
