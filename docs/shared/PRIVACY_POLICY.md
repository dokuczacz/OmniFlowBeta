# OmniFlow Beta Privacy Policy

This privacy policy explains how OmniFlow Beta collects, uses, and stores information related to the multi-user AI agent platform. It applies to the backend services, operator UI, and any tooling maintained within this repository.

## 1. Information we collect

- **Telemetry & logs** – backend functions log execution metadata (timestamps, user identifiers such as `X-User-Id`, tool calls, errors). Logs are retained only as long as needed for troubleshooting and monitoring.
- **Interaction data** – requests/responses paired with agent context may be stored temporarily in Azure Blob Storage under `users/{user_id}/...` (semantic artifacts, WP6 context packs, WP7 manifests). The project uses `save_interaction` to persist conversations and caches.
- **Configuration metadata** – `local.settings.json`, `.env.*`, and any future `config.json` hold operational settings and secrets. Secrets remain only in developer/production environments and never in the repository.

## 2. How we use information

- Improve tool orchestration (WP6 context builder + WP7 indexer) by reusing cache hits and auditing results.
- Provide multi-user isolation and tracing so that each request is scoped by `X-User-Id`.
- Monitor system health with Azure Functions metrics, App Insights, and function keys; debug info is gated by `DEBUG_TOOL_CALL_HANDLER`.

## 3. Third-party services

- **Azure Functions & Storage** – host data and artifacts. Their compliance obligations cover storage/processing for us.
- **OpenAI / Azure OpenAI** – processes text prompts/responses. Only the required prompts/F-values are sent; outputs stored according to our retention policy.
- **Vercel / Next.js UI** (when deployed) – uses `.env` secrets (`AUTH_SECRET`, `AI_GATEWAY_API_KEY`) for authentication and storage proxies.

## 4. Data retention & deletion

- Semantic data created by WP7 is retained in each user’s blob namespace; deleting a user’s blob folder removes their history.
- Cache entries (WP6 context packs) expire after `WP6_CONTEXT_PACK_TTL_SECONDS` (300s by default).
- Rolling back feature gates or `config.json` resets behavioral overrides to the documented defaults without reprocessing data.

## 5. Security

- Secrets live in Azure App settings, `.env` files (ignored by Git), or in Key Vault references. The repo contains only templates (`local.settings.template.json`, `.env.example`).
- Function keys (`FUNCTION_CODE_*`) never appear in commits and are rotated through the Azure Portal when needed.
- Access controls rely on GitHub branch protections, App Service authentication, and operator UI gating.

## 6. Contact & updates

- For questions or new requirements, open an issue in this repo or email the maintainer specified in `docs/shared/USER_MANAGEMENT.md`.
- This policy may be updated to match releases (e.g., Patch 2.0) and new governance needs; the current version is stored at `docs/shared/PRIVACY_POLICY.md`.
