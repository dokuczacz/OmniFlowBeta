# WP6 — Session Restore + Context Builder

- Status: active
- Scope: deterministic context selection + context_pack cache reuse
- Audience: operator + developer

## Scope (WP6)

- Build a deterministic **context selection layer** on top of Blob-first storage + WP7 semantic artifacts.
- Provide a compact, reusable `context_pack.json` that reduces `t_model` and avoids exploratory blob reads.
- Support `context_mode`: `FAST | DEEP | AUTO`.

## Inputs / Source of truth

- User namespace in Blob: `users/{user_id}/...`
- WP7 semantic index: `users/{user_id}/interactions/semantic/index.jsonl`
- Optional user preferences/policy: `users/{user_id}/semantics/preferences.json` (WP6.M1)

## Outputs

- `users/{user_id}/semantics/context_packs/{pack_id}.json`
- Optional: `users/{user_id}/semantics/context_packs/index.jsonl` (append-only index)

## Acceptance criteria (WP6)

- `context_pack` is strict schema-valid and versioned.
- In `FAST` mode the backend performs only bounded reads (prefer WP7 semantic + allowed file list).
- In `DEEP` mode a separate **Context Builder** prompt produces a compact pack and is reused via TTL.

## E2E note (DEEP)

- Known limitation: current e2e flows cannot deterministically force `DEEP` routing, but WP6 logic is verified and stable in local scenarios.

## AUTO routing (initial criteria)

The routing logic should be deterministic and visible in logs.

### Token estimator

- Use a quick deterministic estimator for routing only: `est_tokens ~= ceil(chars/4)`.

### Default thresholds (initial)

- `FAST_MAX_INPUT_TOKENS = 8000`
- `FAST_MAX_SOURCES = 4`
- `FAST_MAX_RAW_BYTES = 64000`
- `DEEP_MAX_PACK_TOKENS = 16000`
- `CONTEXT_PACK_TTL_SECONDS = 300`

### AUTO rules (ordered)

1. If user explicitly sets `context_mode` (`FAST` or `DEEP`) → use it.
2. If intent is session restore/recap (e.g. “co robiliśmy”, “podsumuj”) → `DEEP`.
3. If semantic-only is enough and under `FAST_MAX_INPUT_TOKENS` → `FAST`.
4. If raw reads are needed but within `FAST_MAX_SOURCES/FAST_MAX_RAW_BYTES/FAST_MAX_INPUT_TOKENS` → `FAST`.
5. If any FAST limit exceeded → `DEEP`.
6. If recent quality failures (e.g., 2 retries) → `DEEP`.
7. If a fresh pack exists for `(user_id, intent_key)` within TTL → reuse pack (treat as `FAST`).

## Schema

- `docs/workflow/wp6_context_builder/context_pack.schema.v1.json`

## Logging (WP9)

WP6 decisions should be visible in WP9 execution logs, but WP6 docs intentionally avoid duplicating WP9 schema details.
Keep logging fields minimal and deployment-driven (context mode, reuse, budgets).

