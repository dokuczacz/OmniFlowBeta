# Goal
Build and approve a stateless, backend-first prompt system for OmniFlowBeta Personal Assistance so assistant output is user-facing (not manifest/config dumps), deterministic where required, and compatible with WP6/WP7 contracts.

Status: PLAN ONLY. No implementation before operator approval.

# Inputs and Context
- Primary repo: `C:\AI memory\NewHope\OmniFlowBeta`
- Pattern source repo (stateless prompting reference): `C:\AI memory\CV-generator-repo`
- Product docs (may be partly outdated): `C:\Users\Mariusz\OneDrive\Pulpit\ChatGPT\PersonalAssistance`
- Operator intent (latest):
  - priority now: stabilize OmniFlowBeta after refactor
  - target UX: "personal assistance" quality, but backend-first and stateless
  - LLM role: generate user-facing text from provided/verified data (not runtime manifest output)
  - future AI (planner/ML/RL): plug in gradually, step by step, with learning-by-doing and low-risk shadow rollout
- Proven baselines reported by operator:
  - CV-generator has passing golden E2E and delivered 4 CV/CL outputs without manual intervention
  - OmniFlowCentral is being tested by other users with good ratings
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
7. Role clarity gate:
   - assistant-visible output contains only user-facing response contract (`assistant_text` + optional structured user fields)
   - threshold: internal artifacts (`manifest`, `runtime`, `workflow`, `tests`, raw prompt blocks) never appear in user chat in 10/10 replayed runs
8. Incremental-AI readiness gate (no activation yet):
   - telemetry contract for future decision episodes is present but not controlling runtime decisions
   - threshold: shadow-only switch documented and defaulted OFF

Fallback behavior (mandatory):
- If any contract check fails, force safe fallback message (`No response from assistant.` is acceptable only with structured error metadata) and block publish/deploy until fixed.
- No infinite tool loop: hard-stop after bounded iterations with explicit error code.

# Plan
1. [done] Stabilization baseline and git hygiene (first)
- Freeze current failing scenario pack (S1-S5), capture branch/dirty state, and keep reproducible traces.
- Keep work on `feature/personal-assistance-stateless-prompts`; no destructive cleanup.
- Record current prompt id/version env and active runtime flags.

2. [done] Prompt pipeline audit (source-of-truth and leakage root-cause)
- Trace prompt assembly and response extraction in `tool_call_handler`.
- Identify where manifest/config payload is selected as final assistant text.
- Confirm polling path separation (`get_run_progress` vs run action).

3. [pending] Stateless Personal Assistance contract freeze
- Define compact contract: `system_core`, `runtime_policy`, `context_pack`, `tool_capabilities`, `response_schema`.
- Keep one authoritative prompt registry/dict for handler runtime.
- Map semantic vs deterministic requirements explicitly.

4. [in_progress] Backend prompt compiler and output guard design
- Build deterministic compile order and delimiters.
- Introduce strict output schema for user-facing assistant response.
- Add anti-leak rule: internal manifests/specs blocked from user channel.

5. [pending] WP6/WP7 alignment after contract freeze
- WP6: FAST/DEEP prompt inputs aligned to new context contract and first-call validation.
- WP7: enforce batch-first semantic saver path; clarify cached-path option and guardrails.
- Confirm config defaults/overrides in one place.

6. [in_progress] Verification matrix and focused tests
- L0 metadata checks, L1 sample replays, L2 focused unit/integration checks.
- Add explicit regression test for "manifest dump in chat".
- Add observability assertions (run_progress, prompt id used, response shape).

7. [pending] Stateless continuity cutoff (post-green gate)
- Track `last_response`/`previous_response_id` as a separate rollout control.
- Keep continuation ON only during transport/dispatch stabilization.
- After positive focused tests + smoke, disable continuation carry-over:
  - no persisted `responses_last_response_id`
  - no request `previous_response_id` / cross-turn conversation continuation
- Re-run smoke immediately after cutoff to verify no regression in tool completion and reply quality.

8. [pending] Incremental future-AI track (shadow-only, learning mode)
- Add episode telemetry schema and dataset export path (`labs/ml_lab`-ready), runtime decisions unchanged.
- Define staged learning path: policy-eval -> imitation baseline -> planner shadow -> optional offline RL.
- Add promotion gates so no non-LLM policy controls production without KPI pass.

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
- Delivery strategy agreed with operator:
  - First, "ogarniecie Beta" (stability and output correctness).
  - Second, keep LLM as text generator over verified context.
  - Third, introduce other AI types gradually in shadow mode for empirical learning.
- Python best practices included in this plan:
  - typed contracts/dataclasses, pure compile functions, single source of truth for config/registry, narrow unit tests.
- Cookbook/docs alignment included in this plan:
  - Structured Outputs (strict schemas), Responses tool-loop discipline, prompt caching-friendly stable prefix, bounded retries.
- Decision: `last_response` / `previous_response_id` disconnection is a separate, post-green step (after focused tests) to avoid mixed-cause regressions.
- OpenAI Dashboard prompt handling:
  - dashboard prompt is treated as deployable artifact with explicit id/version pin and rollback reference.
- 2026-02-07 implementation delta:
  - backend leak guard hardened for truncated manifest fragments and full Responses object dumps
  - UI fallback hardened to avoid rendering raw JSON payload dumps when assistant text is missing
  - responses tool source control added: `OPENAI_RESPONSES_TOOL_SOURCE` (`inline`|`dashboard`|`both`), default `inline`
  - inline tools are now loaded from `AGENT_FUNCTIONS_CATALOG.json` (`openai_function_schemas`) for request-time tool declaration
  - registry-dispatch bridge fixed: when registry returns `Tool dispatch not available`, handler now falls back to legacy/proxy dispatch path
  - assistants runtime guard added for invalid non-OpenAI thread ids (`handle_*`), preventing invalid thread reuse
  - MVP UI request runtime set to `responses` to match stateless flow
  - focused regression tests passed: `pytest -q tests/unit/test_execute_tool_call_fallback.py tests/unit/test_response_sanitizer.py tests/unit/test_run_responses_contract.py` (10 passed)

## Git hygiene (milestone-end template)
- `git status -sb`
- `git diff --stat`
- `git add -- <explicit-files>`
- `git commit -m "..."`
- `git push`
