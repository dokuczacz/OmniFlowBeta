# WP2 — Next.js MVP UI (Operator Chat) — Final plan

## Scope

This plan covers the **Next.js MVP UI** living in `ai-chatbot/` (MVP route: `/mvp`).
It focuses on **operator ergonomics** and **leveraging existing backend logic** without introducing true token streaming.

Out of scope (for now):
- Backend streaming / SSE / incremental server events.
- Full auth/OAuth (template auth remains separate).

## Inputs / Outputs

**Inputs (existing backend capabilities):**
- `POST /api/tool_call_handler` (primary orchestrator; returns `response`, `thread_id`, `runtime_used`, `tool_calls_count`, `timings`).
- Direct actions via tool handler:
  - `action=get_interaction_history` (through `tool_call_handler` → `handle_direct_actions`).
- WP7 semantic pipeline endpoints:
  - `wp7_indexer_run` (manual) + artifacts in blob paths (`interactions/semantic/*`, `interactions/portfolio/*`, `interactions/batch/audit.jsonl`).
- Storage tools: `list_blobs`, `read_blob_file`, `read_many_blobs`.

**Outputs (UI features):**
- Stable user selection/confirmation flow.
- Operator debug panel (raw response + key telemetry).
- WP7 semantic DB panel (visibility + manual trigger).
- WP6 context restore/build UI (based on available artifacts, not “session restore”).

## Current state (baseline)

**Streamlit LAB UI implemented:** `frontend/app.py`  
**Next.js MVP UI implemented:** `ai-chatbot/app/mvp/page.tsx` + `ai-chatbot/components/mvp-shell.tsx` + `ai-chatbot/components/mvp-chat.tsx`

### Feature parity snapshot

| Area | Streamlit (frontend/app.py) | Next MVP (/mvp) | Status |
|---|---|---|---|
| Active user | Select + add + switch + storage bootstrap | Select + add + confirm overlay | 🟡 needs fix (“Add/confirm” not fully reliable) |
| Persist thread | Session state | localStorage per user | ✅ |
| Chat UX | Sticky composer + autoscroll + ctrl/cmd+Enter | Sticky composer + autoscroll + Enter send | ✅ |
| Continuous logging | UI toggle → `log_interaction` | Missing | 🟡 add |
| Debug raw response | Expander | Missing | 🟡 add |
| WP7 semantic DB | Missing | Missing | ❌ |
| WP6 context restore/build | Not present | Not present | ❌ |

## Acceptance criteria (global)

1) UI must always send correct `user_id` and persist `thread_id` per user across reload.
2) Operator can see **telemetry** (`runtime_used`, `tool_calls_count`, `timings`) and **raw response** without opening console logs.
3) WP7 status is visible: queue/state/audit/semantic manifest basics and a manual trigger exists.
4) All changes are minimal and reversible.

## Plan (PDCA)

### P — Plan items (ordered)

#### P1 — Fix user selection + confirm overlay (MVP blocking)
**Goal:** user selection works deterministically; confirm step is required before chat; switching user always resets confirm.

**Tasks:**
- Persist + restore `activeUser` and `confirmedUser` correctly on load.
- Ensure “Add user” immediately selects and requires re-confirm.
- Ensure UI never shows chat enabled when user not confirmed.

**DoD:**
- After hard refresh, UI shows the same selected user and confirmed state.
- After switching user, chat is disabled until confirming again.
- Backend receives `X-User-Id` consistently (no `None`).

#### P2 — Frontend debug panel (operator-grade)
**Goal:** parity with Streamlit “Raw backend response”, but in Next MVP UI.

**Tasks:**
- Add a collapsible “Debug” section in sidebar:
  - last request payload (sanitized),
  - last response JSON (pretty),
  - last error (if any),
  - telemetry summary (`thread_id`, `latency_ms`, `runtime_used`, `tool_calls_count`).

**DoD:**
- One click shows the last raw response and key telemetry.

#### P3 — “Continuous logging” toggle (cost/noise control)
**Goal:** parity with Streamlit’s `log_interaction` flag.

**Tasks:**
- Add toggle in UI.
- Include `log_interaction: boolean` in the request payload to backend.

**DoD:**
- Backend honors `log_interaction=false` (no interaction log saved) and UI still works.

#### P4 — WP7 semantic DB panel (“semantic database update” visibility)
**Goal:** operator can inspect WP7 pipeline and trigger indexing manually.

**Tasks:**
- Add “Semantic DB” panel:
  - show last N lines of `interactions/batch/audit.jsonl`,
  - show last N lines of `interactions/semantic/index.jsonl`,
  - show last N lines of `interactions/portfolio/uncategorized.jsonl`,
  - show basic state from `interactions/indexer_state.json` (byte offset + first_pending).
- Add “Run WP7 indexer now” button → call `wp7_indexer_run`.

**DoD:**
- After clicking “Run”, audit/manifest updates are visible (when queue has pending items).

#### P5 — WP6: Context restore/build (rename + implement minimal)
**Goal:** replace “session restore” with deterministic **context pack** build from available artifacts.

**Tasks:**
- Create a UI workflow:
  - “Build context pack” button:
    - reads semantic manifest + selected artifacts (top K by recency/signal_level),
    - produces a context preview (text/JSON) and stores it client-side for the next message.
- Keep it non-invasive: default off, explicit action only.

**DoD:**
- Operator can generate a context pack without scanning raw interaction logs.

### D — Do (implementation rules)
- Implement one plan item per PR/commit group (small changes).
- Add minimal local verification steps for each item.

### C — Check (minimal tests per item)
- P1: reload + switch user + send 1 message; confirm `X-User-Id` and thread persistence.
- P2: send 1 message; confirm debug panel shows raw response + telemetry.
- P3: toggle logging; send 1 message; verify backend interaction log changes accordingly.
- P4: run indexer; verify blob tails change (audit/index/uncategorized).
- P5: build context pack; verify it is used on next request (explicitly visible in debug request payload).

### A — Act (next iteration)
- Only after P1–P3 are stable, start P4 (WP7) and then P5 (WP6).

