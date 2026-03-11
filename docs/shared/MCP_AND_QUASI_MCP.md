# OmniFlow Quasi-MCP Guide

## Status

This integration surface is beta/test.

Test model:

- https://chatgpt.com/g/g-69b01cec119481919adf992756bcde53-omniflow-personal-assistance

## What "quasi-MCP" means here

OmniFlow uses a single HTTP orchestration endpoint with registry-driven tool dispatch and structured JSON contracts.

It is MCP-like in behavior, but not a full MCP transport implementation.

### Similarities

- Tool registry and canonical capability names
- Deterministic argument normalization and validation
- Structured JSON responses and error codes

### Differences from full MCP

- Single HTTP endpoint instead of transport/session protocol
- No stdio transport process model
- Backend-enforced orchestration in one function app

## Core endpoints

- `POST /api/tool_call_handler` - orchestration entry point
- `POST /api/read_many_blobs` - batch retrieval helper
- `POST /api/save_interaction` - interaction ingestion

## Connection paths

### 1. Custom GPT

1. Import OpenAPI schema from `docs/shared/tool_call_handler_openapi.json`.
2. Configure server URL to your deployed function app.
3. Provide function key/auth as required by your deployment.
4. Start with `mail.status`, `mail.authorize`, and `mail.inbox.list` for smoke tests.

### 2. Generic HTTP clients / agents

- Send `action=capability_exec` payloads to `/api/tool_call_handler`.
- Pass user namespace via `X-User-Id` (or explicit user_id in payload if supported).
- Treat response body as JSON contract only.

## Contract references

- OpenAPI: `docs/shared/tool_call_handler_openapi.json`
- Function catalog: `AGENT_FUNCTIONS_CATALOG.json`
- Operator examples: `FUNCTION_CALLS_PLAYBOOK.md`

## Security and isolation notes

- User data is namespaced by user id in blob paths.
- Function app auth/function key must be configured per environment.
- Do not place secrets in repository files.

## Known constraints

- WP6 DEEP path is not always deterministically forceable end-to-end.
- Some integrations require explicit confirmation fields for mutating actions.

## Recommended onboarding sequence

1. Read `README.md`.
2. Follow `docs/shared/DEPLOYMENT.md`.
3. Validate one non-mutating and one mutating capability call.
4. Add integration-specific retries and error handling.
