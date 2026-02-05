# OmniFlowBeta — Tool Handler 1 (tool_call_handler) Implementation Plan

Status: **PLAN ONLY (no implementation until operator approval)**

Owner: operator + Codex

Primary focus repo: `C:\AI memory\NewHope\OmniFlowBeta`

Related repos (integration later in plan):
- `C:\AI memory\NewHope\OmniFlowCentralRepo` (OAuth + dataset tools)
- `C:\AI memory\CV-generator-repo` (out of scope unless explicitly tied in)

---

## 0) Intent + Operator Approval Gates

You asked for **deep planning only** and to **approve the plan before any implementation**.

Approval gates:
1. Approve this plan (document) → only then start implementation.
2. Before any destructive git cleanup (`git clean -fd`, `git reset --hard`) → explicit operator “yes”.
3. Before any Dashboard prompt changes (OpenAI UI) → explicit operator “yes” (because it changes runtime behavior immediately).

---

## 1) Goals (Project-First)

### G1 — Final, stable tool contracts first
Lock a single source of truth for:
- canonical tool names
- parameter aliases
- allowed/required parameters (field-level)
- response envelope and error codes

### G2 — Tool handler 1 refactor to “unified dict / registry”
Make `tool_call_handler` maintainable:
- a single registry defines tools + validation + dispatch
- code structure comparable to “early-senior” maintainability (testable, split modules, minimal special-cases)

### G3 — Datasearch engine next (built on final contracts)
Implement fast, bounded search for agents **without** needing WP6/WP7 changes first.

### G4 — Only then: WP6/WP7 patches
Patch WP6/WP7 once contracts are stable, to avoid rework.

---

## 2) Non-Goals (for the first iteration)

- No “admin UI” build until contracts + datasearch are stable.
- No DB migration (Postgres/Cosmos) until the “agent exchange” blob-first contract proves insufficient.
- No broad repo rewrites; changes should be incremental and reversible.

---

## 3) Current System Inventory (as-is)

### 3.1 Tool handler 1 locations
- Beta tool handler 1: `backend/tool_call_handler/__init__.py`
- Beta tool endpoint modules (in-process): `backend/tools/*.py`
- Shared config snapshot: `backend/shared/tool_handler_config.py`
- Agent tool catalog: `AGENT_FUNCTIONS_CATALOG.json`

### 3.2 Central repo reference (good pattern)
Central already uses:
- `TOOL_SPECS` (tool manifest) + `TOOL_HANDLERS` (dispatch table)
- strict param aliasing + canonical names
Reference: `OmniFlowCentralRepo/OmniFlowCentral/tools_call/__init__.py`

### 3.3 Prompt contracts (Dashboard OpenAI) — must be treated as deploy-time contract
These are not fully controlled in code; some must be set in the OpenAI Dashboard:
- `OPENAI_PROMPT_ID` (main agent):
  - must have the right model selected in the Prompt
  - must have tools attached in the Prompt (code does not pass tools list dynamically)
  - must include instructions for tool usage + (if used) WP6 escalation signal format
- `OPENAI_CONTEXT_BUILDER_PROMPT_ID` (WP6 context builder):
  - must output strictly JSON matching the expected pack schema used by the tool handler
- `OPENAI_INDEXER_PROMPT_ID` (WP7 indexer):
  - must follow strict JSON schema for semantic items (code enforces schema at request-time)

---

## 4) WP6 “What is constructed” (as-is behavior; this is the baseline you asked for)

WP6 in Beta is a routing + context-building layer inside `tool_call_handler`.

### 4.1 Inputs
- `user_message` (from request body)
- `thread_id` (from request body, or created)
- `context_mode` (`AUTO|FAST|DEEP`)
- Blob sources under `users/{user_id}/...`:
  - semantic index JSONL: `interactions/semantic/index.jsonl` (primary cheap source)
  - semantic artifacts: `interactions/semantic/INT_*.json`
  - preferences: `semantics/preferences.json`

### 4.2 FAST mode constructed message (sent to main agent prompt)
- Tool handler builds a bounded FAST context string from WP7 semantic artifacts and injects it:
  - `[FAST_CONTEXT]\n{fast_ctx}\n\n[USER_MESSAGE]\n{user_message}`
- FAST context is bounded by config (`WP6_FAST_MAX_SOURCES`, `WP6_FAST_MAX_RAW_BYTES`, estimator tokens).

### 4.3 AUTO escalation signal (FAST → DEEP)
After the FAST response, the model can request one DEEP escalation:
- Preferred: first-line JSON with `need_deep` + fields
- Fallback token: `__ROUTE_DEEP__`
Tool handler parses it and may run DEEP once.

### 4.4 DEEP mode constructed message (Context Builder + pack reuse)
If DEEP is entered (explicit or escalated):
1) The tool handler calls the Context Builder prompt (`OPENAI_CONTEXT_BUILDER_PROMPT_ID`) with JSON input:
   - `request.user_prompt`
   - `candidate_sources[]` (paths + excerpts)
   - `constraints` (token + bullets + top sources)
2) It expects the Context Builder output to be JSON “pack” (current legacy shape):
   - `mode, summary, bullets, top_sources, pack_tokens_est, coverage, need_more_sources, created_utc`
3) It persists the pack at:
   - `semantics/context_packs/{pack_id}.json`
4) It injects the pack into the main agent input:
   - `[CONTEXT_PACK_JSON]\n{pack_json}\n\n[USER_MESSAGE]\n{user_message}`

### 4.5 Preferences gate (WP6.M1)
- `semantics/preferences.json` controls read allowlisting and history-read disable.
- It is used to block broad browsing and expensive history reads in FAST.

---

## 5) Implementation Plan (Re-ordered per your instruction)

### Phase 0 — Git hygiene + branch strategy (FIRST)
Objective: work from a known state and ensure implementation happens on a new branch.

Steps:
0.1) Confirm current working tree state (`git status --porcelain`) and decide strategy:
  - Option A: stash all (safe)
  - Option B: commit WIP to a temporary branch
  - Option C: destructive reset (requires explicit operator “yes”)
0.2) Create a new branch for the planned work:
  - naming suggestion: `feature/tool-handler-1-registry`
0.3) Ensure tests are runnable in that branch (baseline).

DoD:
- Clean baseline state is reproducible.
- New branch exists and is checked out.

### Phase 1 — Define the unified tool registry contract (NO code yet)
Objective: finalize “final contracts” before touching WP6/WP7.

Deliverables:
1.1) `TOOL_REGISTRY` spec (tool metadata schema):
  - canonical name
  - aliases (tool name + param aliases)
  - allowed fields (from `AGENT_FUNCTIONS_CATALOG.json`)
  - required fields (per tool)
  - dispatch mode: `in_process` | `proxy_router` | `central_http`
  - timeout + safety caps (max files, max bytes, etc.)
  - response envelope normalization rules
1.2) Error contract:
  - standardized error codes: `MISSING_PARAM`, `VALIDATION_FAILED`, `INVALID_TOOL`, `UPSTREAM_ERROR`, `PREFERENCES_BLOCKED`, etc.
1.3) Tool discovery contract:
  - `tools/capabilities` output should be derived from registry (single source of truth).
1.4) Decide datasearch tool contract now (inputs/outputs) so WP6/WP7 can later rely on it.

DoD:
- Operator approves the registry contract and datasearch contract.

### Phase 2 — Implement unified dict/registry (tool handler 1 core refactor)
Objective: implement `TOOL_REGISTRY` and make all tool routing use it.

Steps:
2.1) Create `tool_call_handler/registry.py` (or equivalent) with:
  - `TOOL_REGISTRY = {...}`
  - canonicalization + param alias functions
2.2) Refactor dispatch pipeline into deterministic stages:
  - normalize tool name → apply param aliases → filter allowed fields → validate required fields → dispatch → normalize output
2.3) Remove ad-hoc per-tool filtering tables from handler (replace with registry metadata).
2.4) Add unit tests:
  - registry completeness checks
  - param aliasing correctness
  - required/allowed enforcement

DoD:
- All existing tools still work through the registry with no behavior regression.
- Capabilities endpoint matches registry.

### Phase 3 — Datasearch engine (built on registry)
Objective: add datasearch as a first-class tool and lock its contract.

Contract (draft; finalize in Phase 1):
- Inputs:
  - `q` (string, optional)
  - `tags_any[]`, `tags_all[]` (optional)
  - `category` (optional)
  - `since`, `until` (optional ISO8601)
  - `limit` (default 20)
  - `cursor` (paging)
  - `include_snippets` (bool, default true)
  - `fetch_content` (bool, default false)
- Outputs:
  - `items[]`: `{blob_name, score?, display_name?, summary?, tags?, updated_at, snippet?}`
  - `next_cursor`
  - `source`: `{manifest_used, semantic_index_used}`

Implementation details:
3.1) Primary search index:
  - per-user manifest: `manifests/{user_id}/manifest.json`
3.2) Optional augmentation:
  - if WP7 semantic index exists, allow searching it for additional recall (bounded tail reads).
3.3) Ensure bounded reads:
  - never scan large blobs without explicit `fetch_content=true`
3.4) Add tests:
  - filtering, paging, stable ordering, empty states

DoD:
- Datasearch tool is usable by agents and stable under empty/large datasets.

### Phase 4 — Wire agent loop to registry & “final contracts”
Objective: ensure the main agent prompt uses the final tool names/params.

Steps:
4.1) Update `AGENT_FUNCTIONS_CATALOG.json` to match registry:
  - tool list + schemas
  - examples + gotchas
4.2) Add a “Prompt Contract Checklist” doc:
  - what must be set in Dashboard for `OPENAI_PROMPT_ID`
  - what must be set in Dashboard for `OPENAI_CONTEXT_BUILDER_PROMPT_ID`
  - what must be set in Dashboard for `OPENAI_INDEXER_PROMPT_ID`

DoD:
- Operator can validate prompt configuration without guessing.

### Phase 5 — Only then: WP6/WP7 patching to the finalized contracts
Objective: update WP6/WP7 to rely on registry + datasearch, and to match final contracts.

WP6 patch steps:
5.1) Replace direct reads of semantic index/artifacts with:
  - registry tool calls (same interface the agent uses)
  - or datasearch results → targeted reads (bounded)
5.2) Decide WP6 context pack schema strategy:
  - keep legacy output shape OR migrate to `omniflow.wp6.context_pack.v1`
5.3) Add explicit WP6 routing metadata output for debugging and DoD.

WP7 patch steps:
5.4) Ensure WP7 “semantic saver” is always batch-first by default, and all code paths use the config defaults consistently.
5.5) Define and implement “cached” mode only if contract is clear (what is cached, TTL, invalidation).

DoD:
- WP6/WP7 behavior matches finalized contracts and passes tests.

### Phase 6+ (deferred until after WP6/WP7)
6) Beta ↔ Central OAuth integration (tool handler → Central endpoints)
7) Agent exchange “central DB” (start blob-first JSONL + index)
8) Admin space / control unit

---

## 6) Testing + Validation Strategy (per phase)

- Phase 0: run unit tests baseline.
- Phase 2: registry tests + existing unit tests.
- Phase 3: datasearch unit tests (pure functions + mocked blob reads).
- Phase 5: WP6/WP7 focused tests + “contract tests” to ensure prompt outputs are schema-valid.

Keep test scope limited to repo `tests/` (do not run vendored external test suites).

---

## 7) Risks + Mitigations

- Risk: Dashboard prompt drift breaks runtime behavior.
  - Mitigation: Prompt Contract Checklist + contract tests + strict schema enforcement where possible.
- Risk: Refactor introduces regressions in tool routing.
  - Mitigation: stage refactor via registry with golden tests and minimal behavior changes per PR.
- Risk: Datasearch becomes slow if it scans too much.
  - Mitigation: manifest-first + bounded reads + cursor/paging + explicit fetch_content.

---

## 8) Implementation Start Conditions (when we begin coding)

We begin implementation only after:
1) You approve this plan.
2) You choose the Phase 0 git hygiene option (stash vs WIP commit vs reset).

