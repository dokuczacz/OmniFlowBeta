# Goal
Roll out Personal Assistance (PA) end-to-end based on baseline scope `PA-01..PA-15`, with updated runtime logic:
- default runtime pattern: `one-stage one-phase` per function,
- backend remains source of truth (validation, limits, tool allowlist, state writes),
- LLM is used for semantics and rendering only,
- each function closes with deterministic DoD + live E2E evidence.

# Inputs and Context
## Stable scenario pack
- Repo: `C:\AI memory\NewHope\OmniFlowBeta`
- Baseline scope source: first PA baseline from this chat (PA-01..PA-15 list + artifacts + principles).
- Frozen users for behavior calibration:
  - `default` (reference behavior and universal prompt patterns)
  - `MarioBros` (real operational user with Gmail + TM usage)
- Frozen storage snapshots (informational reference):
  - `tmp/agentdatastorage_users_snapshot_20260210_105740`
  - `tmp/azurite_users_snapshot_20260210_113055`
- Frozen core artifacts (required for active user):
  - `TM.json`, `PS.json`, `LO.json`, `GEN.json`, `SYS.json`, `semantics/preferences.json`
- Gmail prerequisite (for PA-13/14/15 live tests):
  - OAuth token present in `gmail/oauth/<user_id>.json`.

## Runtime assumptions (current target)
- PA intention (`gpt-5-nano`) is source of truth for PA routing (`pa_function_id`).
- Default execution mode for PA functions: single-step with one operational phase/stage.
- Initial default operational marker:
  - `phase=P7`, `stage=S8` for answer/tool execution.
- Intention marker remains routing-oriented:
  - `phase=P4`, `stage=S6`.
- If a function proves unstable in single-step mode, add extra stage only for that function.
- One master plan only: this file is the single SOT; no side plans.
- Context capsule for model input is semantic-only and intention-scoped.
- Context capsule has no trim/size budget in current rollout phase.
- Prompt composition SOT is backend dict registries; dashboard prompt id is anchor/log only.
- `fast/deep` is a deprecated control flag and has no routing authority.
- Routing and execution path are derived only from PA intent + backend policy.
- `fast/deep` may be consumed only as an optional quality hint for rendering.
- Removal gate: remove `fast/deep` runtime path after Wave-2 if TM/Gmail E2E stay green.
- Vector Storage policy is out of scope for this master plan version.

## Deterministic gates (must stay)
- Starter pack gate: no starter pack -> explicit `pa_init` confirmation required.
- Gmail OAuth gate: no token -> fail-fast JSON `409 NOT_AUTHORIZED`.
- Tool payload validation: malformed args -> deterministic JSON error (no silent fallback).
- JSON contracts only (`schema_version` in artifacts and structured responses).
- Capsule scope gate: capsule payload must not include telemetry/system keys (`user_id`, `session_id`, `run_id`, `ts_utc`, `phase`, `stage`, `response_id`, `prompt_id`, `requires_confirmation`, `write_intent`, `tool_budget`).

# Acceptance
## DoD (program-level)
- One master rollout plan governs all PA functions (`PA-01..PA-15`) with explicit WU status.
- For each PA function:
  - pre-agent baseline is defined and passes (dry-run, deterministic checks),
  - live E2E passes via backend HTTP with real OpenAI call path,
  - artifact evidence is persisted and auditable,
  - fallback behavior is deterministic and documented.
- Prompt/payload traceability exists:
  - response ids, intent response ids, phase/stage, prompt id, tools-included are logged.
- Dev run trace artifact exists per run (flaggable):
  - for dev/local runs backend writes one run artifact with routing/payload/tool summary,
  - production can disable this path by env flag.
- OpenAI payload matrix exists and is current (single source of truth for what backend sends).
- Implementation status table is maintained in this file (`DONE|IN_PROGRESS|NOT_STARTED`) for PA-01..PA-15.

## DoD (commands + thresholds + fallback)
- Baseline compile check:
  - `py -3 -m py_compile backend/tool_call_handler/__init__.py backend/shared/openai_tools.py`
  - threshold: exit code `0`.
- Live TM E2E:
  - `py -3 scripts/e2e_pa_live.py --env local --user MarioBros --focus tm`
  - threshold: exit code `0` and TM artifact changed as expected.
- Live Gmail E2E:
  - `py -3 scripts/e2e_pa_live.py --env local --user MarioBros --focus gmail`
  - threshold: exit code `0`, tool flow observed (`gmail_recent_metadata`, `gmail_profile`, `gmail_send`, `gmail_trash|gmail_delete`), and message id consistency for send/delete.
- Dev run artifact check:
  - `py -3 scripts/e2e_pa_live.py --env local --user MarioBros --focus tm`
  - threshold: response contains `run_artifact_path` and blob exists under `users/<user>/semantics/runs/...`.
- Fallback:
  - if OAuth missing: return deterministic `409` and stop (no prompt loop),
  - if payload invalid: return deterministic validation error and stop,
  - if E2E fails: rollback only last WU change, keep previous passing behavior.

## DoD per function (single-step default)
| PA-ID | Function | Live E2E completion signal | Required artifacts |
|---|---|---|---|
| PA-01 | Task Management | list/add/update/complete/delete path works with deterministic confirmations | `TM.json`, `interactions/INT_*.json`, `handles.json` |
| PA-02 | Daily Planning | plan generated from TM/PS/LO and persisted | `LO.json`, `SYS.json`, `interactions/*` |
| PA-03 | Priority Reasoning | priorities recalculated with auditable rationale | `TM.json`, `SYS.json`, `interactions/*` |
| PA-04 | Goal Alignment | tasks mapped to goals and gaps identified | `TM.json`, `PS.json`, `interactions/*` |
| PA-05 | Progress Review | progress report generated from actual artifacts | `GEN.json` or report artifact, `SYS.json` |
| PA-06 | Knowledge Recall | relevant knowledge retrieved with source references | `GEN.json`, `interactions/*` |
| PA-07 | Note & Idea Handling | create/update/delete notes with auditability | `GEN.json`, `SYS.json` |
| PA-08 | Artifact Analysis | uploaded artifact analyzed to strict JSON output | analysis artifact JSON, `interactions/*` |
| PA-09 | Context Integration | context capsule merged from multiple artifacts | capsule artifact JSON, `handles.json` |
| PA-10 | Decision Reflection | reflection output linked to historical evidence | reflection artifact JSON, `interactions/*` |
| PA-11 | Summary & Reporting | system summary generated in strict schema | summary artifact JSON, `interactions/*` |
| PA-12 | Function Proposal | next-step proposals with deterministic structure | proposal artifact JSON, `interactions/*` |
| PA-13 | Mail Management | read + send-to-self + remove test mail | `MAIL.json` snapshot, `interactions/*` |
| PA-14 | Mail Analysis & Triage | classify and summarize requested mailbox slice | `MAIL.json`, `interactions/*` |
| PA-15 | Mail-to-Action Mapping | map mail items to TM/PS actions without duplication | `MAIL.json`, `TM.json`, linkage metadata |

# Plan
1. WU-1: Sync master plan as single SOT (rules, statuses, wave order).
2. WU-2: Sync payload matrix annex to match master decisions.
3. WU-3: Harden semantic-only context capsule (intention-scoped snippets, no trim).
4. WU-4: Revalidate TM/Gmail with live eval + E2E + artifact checks.
5. WU-5: Add ML data-collection labels to intent/run artifacts and canonical schema reference.
6. WU-6: Implement prompt database composer (dict registry) for TM/Gmail.
7. WU-7: Rollout Wave-1 (`PA-13`, `PA-15`, `PA-02`).
8. WU-8: Rollout Wave-2 (`PA-03`, `PA-04`, `PA-05`).
9. WU-9: Rollout Wave-3 (`PA-06`, `PA-07`, `PA-08`).
10. WU-10: Rollout Wave-4 (`PA-09`, `PA-10`, `PA-11`, `PA-12`).
11. WU-11: Remove `fast/deep` runtime path after Wave-2 no-regression gate.
12. WU-12: Decompose `tool_call_handler` after WU-10 is green.
13. WU-13: Run ML shadow-mode gates and prepare replacement go/no-go for nano.

## WU status (current)
| WU | Scope | Status | Evidence |
|---|---|---|---|
| WU-1 | Master plan SOT sync | DONE | this file updated and used as single plan SOT |
| WU-2 | Payload matrix sync | DONE | `tmp/pa_openai_payload_matrix.md` aligned to runtime policy |
| WU-3 | Capsule v2 hardening | DONE | semantic-only capsule + intent-scoped snippets in runtime |
| WU-4 | TM/Gmail revalidation | DONE | `eval_pa_intention_tm/gmail` pass + live e2e TM/Gmail pass |
| WU-5 | ML label contract | DONE | run/intent artifacts include ML label fields (`omniflow.pa.ml_dataset_row.v1`) |
| WU-6 | Prompt DB composer TM/Gmail | DONE | composer metadata present in responses (`composer_*`) |
| WU-7 | Wave-1 (`PA-13`,`PA-15`,`PA-02`) | IN_PROGRESS | runtime scaffolding present; full live DoD not closed per function |
| WU-8 | Wave-2 (`PA-03`,`PA-04`,`PA-05`) | IN_PROGRESS | runtime scaffolding present; full live DoD not closed per function |
| WU-9 | Wave-3 (`PA-06`,`PA-07`,`PA-08`) | IN_PROGRESS | runtime scaffolding present; full live DoD not closed per function |
| WU-10 | Wave-4 (`PA-09`,`PA-10`,`PA-11`,`PA-12`) | IN_PROGRESS | runtime scaffolding present; full live DoD not closed per function |
| WU-11 | Remove `fast/deep` runtime control | DONE | routing forced to FAST, `quality_hint` metadata only |
| WU-12 | `tool_call_handler` decomposition | NOT_STARTED | gated by Wave DoD closure |
| WU-13 | ML shadow-mode gates | NOT_STARTED | gated by Wave DoD closure |

# Commands
- Working dir:
  - `Set-Location "C:\AI memory\NewHope\OmniFlowBeta"`
- Baseline:
  - `py -3 -m py_compile backend/tool_call_handler/__init__.py backend/shared/openai_tools.py`
- TM E2E:
  - `py -3 scripts/e2e_pa_live.py --env local --user MarioBros --focus tm`
- Gmail E2E:
  - `py -3 scripts/e2e_pa_live.py --env local --user MarioBros --focus gmail`
- Snapshot/OpenAI audit helper:
  - `py -3 tmp/fetch_last_responses_snapshot.py`
- Optional targeted intent eval:
  - `py -3 scripts/eval_pa_intention_tm.py`
  - `py -3 scripts/eval_pa_intention_gmail.py`

# Validation
- Pre-agent baseline (must pass before broad live rollout):
  - starter-pack gate behavior,
  - OAuth gate behavior,
  - payload validation behavior,
  - interaction logging durability.
- Live validation:
  - real OpenAI calls for intention and response path,
  - persisted artifacts per function,
  - strict JSON output contracts.
  - capsule contract validation: semantic-only payload (forbidden telemetry/system keys absent),
  - intent-scoped snippet validation: TM intent => no Gmail snippet; Gmail intent => no TM snippet.
- Latency validation:
  - track `p50/p95` for intention call and full response flow,
  - compare before/after major prompt/context changes.
  - monitor payload growth under no-trim policy before introducing any budget policy.

# Recovery
- Keep changes WU-scoped and reversible.
- If a WU fails DoD:
  - revert only that WU delta,
  - keep previous passing WU frozen,
  - continue with smallest deterministic fix.
- If single-step is unstable for specific function:
  - introduce function-specific extra stage, do not globalize complexity.

# Notes
- Requirements split:
  - Semantic: intent interpretation, summaries, prioritization narrative.
  - Deterministic: gates, contracts, tool payloads, artifact persistence, DoD checks.
- Backend-first rule holds: UI does not own phase/stage orchestration.
- Current dict-compliance fact:
  - OpenAI request kwargs are dict-based in backend,
  - some prompt/input bodies are still serialized strings and are tracked in payload matrix for migration.
- Operational hints (`requires_confirmation`, `write_intent`, `tool_budget`) remain in run metadata only, never in model capsule.
- Canonical ML dataset row schema: `omniflow.pa.ml_dataset_row.v1`.

## ML data collection contract
- Required labels in new intent/run artifacts:
  - `final_resolved_intent`
  - `resolved_slots`
  - `execution_outcome`
  - `correction_signal`
  - `corrected_intent`
  - `source` (`real|synthetic`)

## Implementation status vs DoD
| PA-ID | Function | Status |
|---|---|---|
| PA-01 | Task Management | DONE |
| PA-02 | Daily Planning | IN_PROGRESS |
| PA-03 | Priority Reasoning | IN_PROGRESS |
| PA-04 | Goal Alignment | IN_PROGRESS |
| PA-05 | Progress Review | IN_PROGRESS |
| PA-06 | Knowledge Recall | IN_PROGRESS |
| PA-07 | Note & Idea Handling | IN_PROGRESS |
| PA-08 | Artifact Analysis | IN_PROGRESS |
| PA-09 | Context Integration | IN_PROGRESS |
| PA-10 | Decision Reflection | IN_PROGRESS |
| PA-11 | Summary & Reporting | IN_PROGRESS |
| PA-12 | Function Proposal | IN_PROGRESS |
| PA-13 | Mail Management | IN_PROGRESS |
| PA-14 | Mail Analysis & Triage | DONE |
| PA-15 | Mail-to-Action Mapping | IN_PROGRESS |

## Rollout waves (future)
- Wave-1: `PA-13`, `PA-15`, `PA-02`
- Wave-2: `PA-03`, `PA-04`, `PA-05`
- Wave-3: `PA-06`, `PA-07`, `PA-08`
- Wave-4: `PA-09`, `PA-10`, `PA-11`, `PA-12`

## Progress log
- 2026-02-11: master plan consolidated from prior execplans (`tm_gmail_minimal`, `pa_gmail_prompting`, `pa_rollout`, `pa_scope_e2e`).
- 2026-02-11: nano intention `store` switched to `true` for traceability in OpenAI logs.
- 2026-02-11: operator decision applied:
  - postpone earlier plan deltas #1 and #2,
  - keep payload matrix unchanged,
  - implement dev run artifact per run with flag-based disable in production.
- 2026-02-11: nano intention contract hardened to minimal semantic schema (`primary/secondary/slots`) with deterministic backend normalization to PA v3 output.
- 2026-02-11: intention eval status after hardening:
  - `scripts/eval_pa_intention_tm.py`: `13/13` pass,
  - `scripts/eval_pa_intention_gmail.py`: `6/6` pass (including list vs summarize split).
- 2026-02-11: nano baseline upgraded to sparse ranking schema `pa_intention_min_v2`:
  - `primary {pa_id,intent,score,is_selected}`,
  - `alternatives[] {pa_id,intent,score,is_selected}`,
  - `slots {count,task_index,email_ref,query}`,
  - `signals {is_gmail,is_tm,has_write_intent}`.
- 2026-02-11: capsule policy locked to semantic-only + intention-scoped snippets + no-trim.
- 2026-02-11: ML data-collection labels planned as mandatory fields in intent/run artifacts.
- 2026-02-11: prompt composer integrated for TM/Gmail (`composer_matrix_id`, `composer_block_ids`, `composer_schema_id`, `composer_tools_id` logged in responses metadata).
- 2026-02-11: WU-7..WU-10 rollout scaffolding started:
  - prompt/tool/schema dict registries extended for PA-01..PA-15,
  - backend runtime tool include + prefetch defaults added for non-TM/Gmail functions.
- 2026-02-11: WU-7..WU-10 status clarification:
  - no promotion to DONE until each PA function in the wave has one auditable live run and explicit DoD evidence,
  - temporary helper `scripts/e2e_pa_functions_live.py` exists locally but is ignored by `.gitignore` (`scripts/*`), so it is not yet a tracked SOT validation script.
- 2026-02-11: WU-11 implemented (policy change):
  - `fast/deep` no longer controls routing,
  - runtime path is forced to FAST,
  - original `fast/deep/auto` value is retained only as `quality_hint` in metadata.
- 2026-02-11: test alignment to current PA contract completed:
  - `tests/e2e` moved off legacy `_pa_allowed_tools_for_stage_phase` assumptions,
  - `tests/e2e` current result: `256 passed, 88 skipped, 0 failed`.
- 2026-02-11: root cause fix for `MAIL.json` not found:
  - deterministic prefetch is executed also in single-step PA mode,
  - Gmail prefetch persists `MAIL.json` snapshot from `gmail_recent_metadata`,
  - verified by `tool_exec/read_blob_file MAIL.json` returning success for `MarioBros`.
- 2026-02-11: parallel live load smoke executed:
  - users `E2E_Load_A`, `E2E_Load_B`, `E2E_Load_C` initialized via `pa_init`,
  - concurrent TM live runs passed (`TM.json` created/updated, interactions persisted),
  - `MarioBros` Gmail live run passed with intent artifact increment and `MAIL.json` available.

## Next major refactor (post-rollout)
- `function-matrix composer (pre-refactor prerequisite)`:
  - introduce backend SOT matrices: `pa_functions_catalog` (PA->intents), `pa_prompt_matrix`, `pa_tool_matrix`, `pa_output_schema_matrix`, `pa_composition_rules`,
  - implement deterministic composer: `initial block + function blocks (1..N) + merged toolset + selected output schema`,
  - start with TM+Gmail, then extend to PA-01..PA-15.
- `order rule`:
  - apply matrix-composer first, stabilize E2E/contracts, then split `tool_call_handler` modules.
- `dict-like OpenAI inputs (hardening)`:
  - migrate PA intention/context builder/main run iteration-0 from freeform string `input` to structured input items/object envelopes,
  - keep strict output schemas; add tests that fail when critical PA paths send raw concatenated prompt strings.
- `tool_call_handler decomposition (size/complexity)`:
  - split `backend/tool_call_handler/__init__.py` into domain modules (`runtime_responses`, `intent_router`, `context_builder`, `pa_prefetch`, `response_finalize`, `http_actions`),
  - keep one thin Azure entrypoint only (routing + error boundary), move logic to importable modules.
- `Refactor DoD`:
  - matrix-composer drives prompt/tool/schema selection deterministically for TM+Gmail before file decomposition,
  - functional parity for TM/Gmail E2E and intention eval (`scripts/eval_pa_intention_tm.py`, `scripts/eval_pa_intention_gmail.py`) remains green,
  - no regression in run artifacts/log joins (`response_id`, `intent_response_id`, `phase`, `stage`, `tools_included`),
  - `tool_call_handler` file size reduced materially (target: no single module acting as monolith).
