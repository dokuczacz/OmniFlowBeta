# Documentation Standard (OmniFlowBeta)

## Goals

- Keep docs **deployment-oriented**: explain what must be true in prod and how to verify it.
- Keep docs **deterministic**: prefer contracts, schemas, inputs/outputs, and stable paths over narratives.
- Keep docs **minimal and reversible**: avoid long tutorials and duplicated content.

## Information weighting (what we document more vs less)

Prioritize documentation by impact:

1. **Semantics and context (WP6/WP7)**: what is stored, how it is created, how it is consumed, and how to verify.
2. **Public contracts**: HTTP request/response shapes, blob paths, JSON schemas, and invariants.
3. **Deployment/runbooks**: required env vars, rollout steps, rollback switches.
4. **Basics** (telemetry, generic cost tips): keep as short checklists or links, avoid re-explaining fundamentals.

## File header template (recommended)

Start each non-trivial doc with:

- **Status**: draft | active | archived
- **Scope**: what is covered (and what is explicitly out of scope)
- **Audience**: operator | developer | both
- **Inputs / Outputs**: explicit contracts (paths, schemas, payloads)
- **Acceptance**: how to verify (minimal, deterministic)
- **Rollback** (when applicable): the env flag(s) or switch to disable/revert

## Where things live

- `docs/`:
  - Project-level summaries, WP-level docs (e.g., WP7 indexer)
- `docs/shared/`:
  - Contracts, deployment/runbooks, templates
- `docs/workflow/`:
  - Workflow-specific artifacts (schemas, WP9 reporting utilities)

## Naming conventions

- Prefer stable names: `WP6_...`, `WP7_...`, `..._STANDARD.md`, `..._README.md`.
- Keep blob paths in backticks and always include the `users/{user_id}/...` prefix when describing storage.

