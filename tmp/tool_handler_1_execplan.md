# Goal
Refactor **OmniFlowBeta** “Tool Handler 1” (`backend/tool_call_handler/__init__.py`) into a **manifest/registry-driven** runtime with a clear data contract, bounded datasearch, and then align **WP6** + **WP7** behavior on top of those final contracts (no rework).

# Inputs and Context
- Repo (primary): `C:\AI memory\NewHope\OmniFlowBeta`
- Main target file: `backend/tool_call_handler/__init__.py`
- Tool manifest/candidate source-of-truth: `AGENT_FUNCTIONS_CATALOG.json`
- WP6 docs/schemas: `docs/workflow/wp6_context_builder/`
- WP7 code: `backend/shared/wp7_indexer.py` (+ `backend/wp7_indexer_*`)
- Central patterns (reference, not changed unless explicitly planned): `C:\AI memory\NewHope\OmniFlowCentralRepo`
- Architecture handoff notes (best practices extraction): `C:\Users\Mariusz\OneDrive\Pulpit\Architecture-Analysis\cv-generator-handoff\omniflowbeta\OmniFlowBeta_chunk_001.md`
- OpenAI references (for implementation details, not copied into code blindly):
  - Prompt caching guide: `https://platform.openai.com/docs/guides/prompt-caching`
  - Structured outputs guide: `https://platform.openai.com/docs/guides/structured-outputs`
  - Prompt objects / prompt IDs: `https://platform.openai.com/docs/guides/prompting`
- Python best-practice anchors (apply during implementation)
  - Type-first contracts: `dataclasses` / `pydantic` models as schema sources of truth (generate strict JSON schema where possible)
  - Small modules, explicit boundaries (registry / dispatch / wp6 / wp7 / datasearch) to avoid a “god file”
  - Determinism: stable ordering, explicit defaults, pure functions for compile/validate steps
  - Explicit error taxonomy + structured logs/events (no silent fallbacks)
  - Tests as spec: contract tests first, then behavioral regressions (avoid snapshotting huge payloads)

# Acceptance
## A. Repo safety gates
- **No implementation starts** until operator explicitly approves this ExecPlan.
- **No destructive cleanup** (`git reset --hard`, `git clean -fd`) without explicit operator “YES”.
- **No OpenAI Dashboard / Prompt changes** (prompt objects, prompt versions, prompt IDs) without explicit operator “YES”.

## B. Tool Handler 1 refactor outcomes
- `backend/tool_call_handler/__init__.py` becomes a thin entrypoint that delegates to:
  - `tool_registry` (single source of truth)
  - `dispatch` pipeline (canonicalize → validate → execute → normalize)
  - `datasearch` (bounded retrieval)
  - `wp6` / `wp7` modules that consume the registry (no ad-hoc tool maps)
- Tool allowlist is **manifest/registry-driven** (no implicit tool execution).
- A standard **ToolResult envelope** exists (success/error) and is enforced by tests.

## C. WP6 after changes (construction contract)
- **WP6 FAST** (first call of agent): validates payload strictly and produces a deterministic **ContextPack v1** with:
  - `schema_version`
  - `run_id` / `correlation_id`
  - `budgets` (token/byte limits)
  - `layers` (L0-L3), where L0/L1 are always present and L2/L3 are bounded & optional
  - `preferences` normalized (defaults applied, unsafe values rejected)
- **WP6 DEEP**: optional capsule that expands ContextPack using bounded datasearch + targeted reads; never full-scan by default.
- Validation failures return `VALIDATION_FAILED` with a minimal, actionable error payload (no silent fallback).

## D. WP7 after changes (cost + batching contract)
- Semantic saver/indexer **always** uses a batch-capable path (no per-item “normal call” when batch input exists).
- Supports “cached” runs via prompt caching best practices:
  - stable prompt prefix + stable tool list
  - consistent `prompt_cache_key`
  - optional `prompt_cache_retention=24h` when supported/approved
- Idempotency keys per chunk prevent duplicate writes.

## E. Verification signals (commands)
Run from `C:\AI memory\NewHope\OmniFlowBeta`:
- `git status -sb` → clean working tree on implementation branch
- `pytest -q` → all tests green
- Focused smoke: minimal local invocation for tool handler 1 (exact command to be added once baseline entrypoints are confirmed in Stage 0)

## F. Pre-agent gate (Dashboard prompt IDs)
Before wiring agents/prompt IDs into the runtime:
- A “pre-agent baseline (dry-run)” passes (backend orchestration works without dashboard prompt edits).
- Prompt object variables + required hard-constraints that must live in the dashboard prompt are documented in `docs/prompt_contract_checklist.md` (planned artifact).

# Plan
> **Order constraint (operator request):** clean git + new branch → unified dict/registry → datasearch → only then WP6/WP7.

1) **Git hygiene + baseline capture** (non-destructive)
   - Record current branch + status, decide: stash vs WIP commit vs (operator-approved) destructive reset.
   - Capture 3–5 baseline flows for Tool Handler 1 (requests + expected outputs) as a reproducible checklist.
2) **Unified registry + contracts v1 (single source of truth)**
   - Define canonical contracts (ToolSpec, ToolCall, ToolResult, ErrorCodes).
   - Implement `TOOL_REGISTRY` that loads from `AGENT_FUNCTIONS_CATALOG.json` (or a v1 registry file derived from it) and validates on startup.
   - Add a minimal contract test suite (schema loads + registry integrity).
3) **Dispatch pipeline refactor (registry-driven)**
   - Implement deterministic dispatch: canonicalize tool name → apply aliases → validate params → execute handler → normalize ToolResult.
   - Migrate a small, representative set of tools first (2–3) to de-risk design, then migrate the remainder.
4) **Datasearch engine (bounded retrieval)**
   - Add `datasearch` ToolSpec to registry with paging/cursor/limits.
   - Implement bounded search over manifest-known stores + optional semantic tail (strict caps; no full scans by default).
   - Add tests for stable ordering, paging, empty/large cases, and “boundedness” (fails closed).
5) **WP6 patch (after contracts are stable)**
   - Implement WP6 FAST/DEEP as registry-aware components (or “capsules” if we adopt that abstraction).
   - Add strict first-call payload validation + deterministic ContextPack v1 output.
   - Add focused tests: schema compliance + budgets + invalid payload error contract.
6) **WP7 patch (after WP6 is stable)**
   - Make semantic saver batch-first (micro-batching or OpenAI Batch API—decision in Notes).
   - Add caching-friendly prompt compilation (static prefix first; stable `prompt_cache_key`).
   - Add tests: batching behavior, idempotency, retry safety.
7) **Deferred milestone (post-approval): OAuth + Central exchange DB + Admin**
   - Connect tool handler 1 agent flow to OAuth entrypoints (reference Central repo).
   - Design a central “agent exchange point” (reports/requests/profiles) with search indexing.
   - Add admin/control surface + a specialized admin agent (operator-owned scope decisions).

# Commands
## Stage 0 (non-destructive)
Run from `C:\AI memory\NewHope\OmniFlowBeta`:
```powershell
git status -sb
git diff --stat
git log -n 3 --oneline
```

## Later (once approved)
- Branch creation, test runs, and focused smokes will be added here as exact copy/paste commands once Stage 0 establishes the baseline entrypoints.

# Validation
- Unit tests: registry integrity, schema loading, dispatch errors, datasearch paging/boundedness, WP6 ContextPack compliance, WP7 batching/idempotency.
- Golden tests: routing/trigger selections (if/when a trigger engine is adopted).
- Cost sanity: verify `usage.prompt_tokens_details.cached_tokens` is visible in logs when prompt caching is effective (requires real API calls; operator decides).

# Recovery
- Prefer safe recovery first: stash/WIP commit on a separate branch.
- If a refactor step breaks behavior: revert the last small migration (keep changes as small increments).
- Keep contracts backward-compatible via versioned schema (`schema_version`) and adapters; remove legacy only after golden tests.

# Notes (decisions + rationale; append-only)
- Best practice extracted from `cv-generator-handoff` notes: **deterministic JSONL reporting** with a dedicated writer, append-only semantics, and traceability via IDs (useful for ToolResult logs and WP6/WP7 audit trails).
- “Capsule runtime / quasi‑MCP”: treated as an **optional** unifying abstraction; we can implement the registry+dispatch+datasearch first and only then decide if capsules add net value vs. simpler modules.
- WP7 batching decision point:
  - Option A: internal micro-batching inside Tool Handler (single Responses call with batch payload)
  - Option B: OpenAI Batch API for async cost/throughput (requires workflow fit; operator approval)
- Prompt objects / Prompt IDs: plan assumes some constraints live in dashboard prompt definitions; changes there are gated and documented before any integration.
- Cookbook alignment (applied as acceptance criteria, not “nice-to-have”)
  - Prompt caching: stable prefix first; stable tool list; consistent `prompt_cache_key`; optionally `prompt_cache_retention=24h` (operator-approved).
  - Structured outputs: prefer strict schema enforcement at the API boundary; otherwise validate+retry+fail-closed.
  - Prompt objects / IDs: treat dashboard prompts as versioned artifacts; keep a checklist of required “must live in prompt” constraints before wiring IDs into runtime.
