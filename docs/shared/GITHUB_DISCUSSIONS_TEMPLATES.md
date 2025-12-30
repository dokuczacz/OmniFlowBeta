# GitHub Discussions templates (copy/paste)

- Status: active
- Audience: maintainers

Two templates:

1. Project overview (current capabilities + Patch 2.0 checkpoints)
2. Demo usage (what to try + what to verify)

---

## Discussion 1 — OmniFlow Beta: current capabilities + Patch 2.0 status

**Goal:** keep a single “source of truth” thread about what OmniFlow can do today and what’s next.

### What OmniFlow is

OmniFlow Beta is a multi-user AI agent backend (Azure Functions + Azure Blob Storage) with a Next.js UI. It is designed to work as a Custom GPT Actions backend and/or a general tool-call backend for LLM agents.

### Core capabilities (today)

- **Multi-user isolation:** `X-User-Id` header → storage under `users/{user_id}/...`
- **Deterministic tool orchestration:** `POST /api/tool_call_handler` using Responses tool-loop (runtime: `responses|assistants|auto`)
- **Storage tools:** list/read/upload/add/update/remove + `read_many_blobs` (batch multi-read)
- **WP7 semantic pipeline (batch-first):**
  - queue: `interactions/indexer_queue.jsonl`
  - state: `interactions/indexer_state.json`
  - artifacts: `interactions/semantic/{interaction_id}.json`
  - manifest: `interactions/semantic/index.jsonl`
  - uncategorized portfolio: `interactions/portfolio/uncategorized.jsonl`
- **WP6 context builder + cache:** builds a `context_pack` from WP7 artifacts (bounded reads + reuse)

### Patch 2.0 checkpoints

- OK **WP1**: Responses dual runtime + deterministic tool loop
- OK **WP2**: Next UI (Streamlit is legacy)
- OK **WP6**: context builder + cache (note: e2e cannot deterministically force `DEEP`)
- OK **WP7**: semantic indexer (batch-first)
- OK **WP9**: reporting JSONL (local strict writer)

---

## Discussion 2 — OmniFlow Beta: demo usage + verification checklist

### Recommended first tests

- Start a new session with a distinct `user_id`.
- Confirm `list_blobs` shows only your namespace.
- Write + update + delete a small record in `TM.json`.
- Use `read_many_blobs` to read multiple files in one tool call.
- After a few interactions, verify WP7 artifacts exist under `interactions/semantic/`.

### What to watch for

- Correct propagation of `X-User-Id` across all tool calls.
- Bounded reads (prefer WP7 semantic manifest/artifacts instead of raw history scans).
- Stable thread handling per user.

### Legacy note

- Streamlit demo UI is legacy/LAB; primary UI is Next.js.

