# Goal
Build and approve a stateless, backend-first prompt system for OmniFlowBeta Personal Assistance so assistant output is user-facing (not manifest/config dumps), deterministic where required, and compatible with WP6/WP7 contracts.

Status: PLAN ONLY. No implementation before operator approval.

# Inputs and Context
- Primary repo: `C:\AI memory\NewHope\OmniFlowBeta`
- Pattern source repo (stateless prompting reference): `C:\AI memory\CV-generator-repo`
- Product docs (may be partly outdated): `C:\Users\Mariusz\OneDrive\Pulpit\ChatGPT\PersonalAssistance`
- Known issue evidence:
  - repeated `/api/tool_call_handler` requests are UI progress polling against backend action `get_run_progress`
  - wrong assistant output shape (manifest/spec JSON shown in chat)
  - response id to inspect: `resp_053c2d62307baa9f0069865754f4208191985cfdcbe188e12c`
- Key current code paths:
  - `backend/tool_call_handler/__init__.py`
  - `backend/tool_call_handler/dispatch.py`
  - `backend/tool_call_handler/wp6/*`
  - `backend/tool_call_handler/wp7/*`
  - `backend/shared/tool_handler_config.py`
  - `backend/shared/tool_specs.py`
  - tests: `tests/unit/test_wp6_*`, `tests/unit/test_wp7_*`, `tests/unit/test_tool_registry.py`

## Stable scenario pack
Frozen for planning and first validation run:
1. S1: "normal user query" path through `/api/tool_call_handler` with `action=run` (expected natural assistant reply).
2. S2: progress polling path with `action=get_run_progress` (expected status-only JSON, no model call side effects).
3. S3: WP6 FAST context call with minimal dataset (bounded context, no manifest in user reply).
4. S4: WP7 semantic saver/indexer call in configured `batch` mode.
5. S5: failure probe using known bad response `resp_053c2d...` for postmortem comparison.

If operator wants different scenarios, replace this pack before implementation.

# Acceptance
## DoD
All checks must pass in OmniFlowBeta repo (`C:\AI memory\NewHope\OmniFlowBeta`):
1. Prompt contract and routing checks:
   - `pytest -q tests/unit/test_wp6_routing.py tests/unit/test_wp6_schemas.py tests/unit/test_tool_registry.py`
   - pass rate: 100%
2. Prompt output-shape guard:
   - add/execute focused test ensuring assistant-visible response is not raw manifest/capsule/system payload for S1
   - success threshold: 0 leaks across 10 repeated runs
3. Polling isolation:
   - verify `action=get_run_progress` path does not trigger prompt/model run
   - success threshold: 0 model invocations in polling-only replay
4. WP6 context gate:
   - FAST path returns bounded context and expected schema fields
   - threshold: schema valid in 10/10 runs
5. WP7 batch gate:
   - indexer/saver uses batch-mode contract (not single-item fallback unless explicit)
   - threshold: mode==`batch` in config and runtime trace for test scenario
6. Pre-agent baseline dry-run:
   - backend deterministic dry-run (mocked/disabled model) passes before live LLM enablement
   - threshold: all dry-run checks green

Fallback behavior (mandatory):
- If any contract check fails, force safe fallback message (`No response from assistant.` is acceptable only with structured error metadata) and block publish/deploy until fixed.
- No infinite tool loop: hard-stop after bounded iterations with explicit error code.

# Plan
1. [pending] Git hygiene and branch baseline (first)
- Capture clean reproducible state, then create branch `feature/personal-assistance-stateless-prompts`.
- Record current prompt id/version env and active runtime flags.

2. [pending] Prompt pipeline audit (source-of-truth and leakage path)
- Trace prompt assembly and response extraction in `tool_call_handler`.
- Identify where manifest/config payload is selected as final assistant text.
- Confirm polling path separation (`get_run_progress` vs run action).

3. [pending] Stateless prompt contract design (Personal Assistance specific)
- Define compact contract: `system_core`, `runtime_policy`, `context_pack`, `tool_capabilities`, `response_schema`.
- Keep one authoritative prompt registry/dict for handler runtime.
- Map semantic vs deterministic requirements explicitly.

4. [pending] Prompt compiler plan (backend-first, deterministic)
- Build deterministic compile order and delimiters.
- Introduce strict output schema for user-facing assistant response.
- Add anti-leak rule: internal manifests/specs blocked from user channel.

5. [pending] WP6/WP7 integration plan after contracts are frozen
- WP6: FAST/DEEP prompt inputs aligned to new context contract and first-call validation.
- WP7: enforce batch-first semantic saver path; clarify cached-path option and guardrails.
- Confirm config defaults/overrides in one place.

6. [pending] Verification matrix and minimal test operator sequence
- L0 metadata checks, L1 sample replays, L2 focused unit/integration checks.
- Add explicit regression test for "manifest dump in chat".
- Add observability assertions (run_progress, prompt id used, response shape).

7. [pending] Rollout and governance
- Shadow mode -> gated mode -> full mode rollout steps.
- Operator controls for prompt id/version, safe rollback pointer, and dashboard prompt sync checklist.
- Document exact deploy checklist and rollback command sequence.

# Commands
All commands from `C:\AI memory\NewHope\OmniFlowBeta`.

## Baseline and branch
- `git status -sb`
- `git rev-parse --abbrev-ref HEAD`
- `git checkout -b feature/personal-assistance-stateless-prompts`

Expected signal: new branch created, dirty files explicitly listed (none hidden).

## Prompt/runtime config snapshot
- `python -c "from backend.shared.tool_handler_config import build_tool_handler_config as b; c=b(); print({'wp6_responses_stateless':c.wp6_responses_stateless,'wp7_indexer_mode':c.wp7_indexer_mode,'openai_indexer_prompt_id':bool(c.openai_indexer_prompt_id)})"`

Expected signal: explicit booleans/values printed for run-critical flags.

## Focused verification sequence (post-implementation only)
- `pytest -q tests/unit/test_wp6_routing.py tests/unit/test_wp6_schemas.py tests/unit/test_wp6_validation.py`
- `pytest -q tests/unit/test_wp7_indexer.py tests/unit/test_wp6_wp7.py`
- `pytest -q tests/unit/test_tool_registry.py tests/unit/test_dispatch.py`

Expected signal: all selected tests green; no broad suite needed initially.

# Validation
Validation ladder (smallest-first):
- L0: config + route metadata checks (prompt id, mode flags, action branching)
- L1: replay 5-10 scenario-pack requests and inspect output shape
- L2: focused unit/integration tests around prompt compiler + handler finalization
- L3: optional before/after latency/cost sample on S1-S4

Pass criteria:
- No assistant-visible manifest/system payload leaks
- Polling path isolated from model run path
- WP6/WP7 contracts remain schema-valid
- Deterministic fallback for model/contract failures

# Recovery
- Idempotence: all plan steps are read-first; implementation steps must be rerunnable.
- Retry: if prompt extraction fails, log raw response metadata and retry once with guarded parser.
- Rollback:
  - keep previous prompt id/version as rollback target
  - revert to previous handler response extraction function if leakage reappears
  - disable new prompt compiler via feature flag until fixed

# Notes
- Requirements split (semantic vs deterministic):
  - Semantic: intent style, personalization wording, response quality.
  - Deterministic: routing, schema validation, tool allowlist, anti-leak filtering, loop bounds, polling isolation.
- Python best practices included in this plan:
  - typed contracts/dataclasses, pure compile functions, single source of truth for config/registry, narrow unit tests.
- Cookbook/docs alignment included in this plan:
  - Structured Outputs (strict schemas), Responses tool-loop discipline, prompt caching-friendly stable prefix, bounded retries.
- OpenAI Dashboard prompt handling:
  - dashboard prompt is treated as deployable artifact with explicit id/version pin and rollback reference.

## Git hygiene (milestone-end template)
- `git status -sb`
- `git diff --stat`
- `git add -- <explicit-files>`
- `git commit -m "..."`
- `git push`
