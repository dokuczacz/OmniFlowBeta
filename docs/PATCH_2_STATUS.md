# Patch 2.0 — status (source of truth)

- Status: active
- Audience: operator + developer
- Scope: what is “done” and what remains for deployment

## Done (Patch 2.0 core)

- OK WP1: Responses + dual runtime + deterministic tool loop
- OK WP2: Next UI (Streamlit is legacy)
- OK WP4: per-user isolation (`X-User-Id` → `users/{user_id}/...`)
- OK WP5: storage tools (incl. `read_many_blobs`)
- OK WP6: context builder + cache reuse (note: e2e cannot deterministically force `DEEP`)
- OK WP7: semantic indexer (batch-first; queue → artifacts → manifest)
- OK WP9: reporting (local JSONL writer)
- OK Monitoring/metrics: done in prod (per project update)
- OK Email lifecycle parity: backend `gmail_trash` + `gmail_delete` implemented in bridge
- OK Email side-effect traceability: `audit_id` returned for `gmail_send|gmail_trash|gmail_delete`
- OK PA confirmation gate: Gmail `send/trash/delete` flagged as confirmation-required paths

## Remaining (deployment backlog)

- X UI integration: connect `ai-chatbot/` chat functionality into the preferred UI in `ui_next/` (`docs/shared/WP2_NEXT_UI_PLAN.md`)
- X WP8: security/auth/quotas (production hardening)
- X WP11: CI/hardening/prod polish
- X WP3: vector memory/RAG (parked)
- X Live E2E destructive scenario rollout (operator-run only with explicit flags and test mailbox)

## High-signal docs

- WP7 Semantics: `docs/WP7_Indexer_Batch.md`
- WP6 Context Builder: `docs/workflow/wp6_context_builder/README.md`
- Deployment: `docs/shared/DEPLOYMENT.md`
- Tool calls: `FUNCTION_CALLS_PLAYBOOK.md`

## Legacy handover document

The older handover file is kept as historical background and may contain outdated statuses:

- `docs/OmniFlow_Project_Summary_and_Next_Steps.md`

