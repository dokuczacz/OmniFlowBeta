# GitHub Discussions templates (copy/paste)

These are ready-to-post templates for two discussions:
1) Project overview (current capabilities + roadmap checkpoints)
2) Demo usage (how to access + what to try)

---

## Discussion 1 — OmniFlow Beta (Project): current capabilities + roadmap (Patch 2.0)

**Goal:** keep a single “source of truth” thread about what OmniFlow Beta can do today, and what’s next.

### What OmniFlow is
OmniFlow Beta is a multi-user AI agent backend (Azure Functions + Azure Blob Storage) with a Streamlit LAB UI. It’s designed to work as a Custom GPT Actions backend and/or a general tool-call backend for LLM agents.

### Core capabilities (today)
- **Multi-user isolation:** `X-User-Id` header → storage under `users/{user_id}/...`
- **Deterministic tool orchestration:** `POST /api/tool_call_handler` using **Responses** tool-loop (runtime selectable: `responses|assistants|auto`)
- **Storage tools:** list/read/upload/add/update/remove/manage (plus `read_many_blobs` for batch multi-read)
- **Session handles:** `handles.json` tracks mapping for conversation continuity (Responses ids + legacy thread id)
- **WP7 semantic pipeline (batch-first):**
  - queue: `interactions/indexer_queue.jsonl`
  - state: `interactions/indexer_state.json`
  - artifacts: `interactions/semantic/{interaction_id}.json`
  - manifest: `interactions/semantic/index.jsonl`
  - uncategorized portfolio: `interactions/portfolio/uncategorized.jsonl`

### Design rules (important)
- Secrets are never committed (local-only `backend/local.settings.json`, Streamlit `frontend/.streamlit/secrets.toml`).
- Append-only logs where possible (JSONL) + deterministic writers for agent-generated artifacts.
- Prompt configuration is a source of truth for tool availability in Responses runtime (no silent fallback).

### Roadmap checkpoints (Patch 2.0)
- ✅ **WP1**: Responses dual runtime + deterministic tool loop
- ✅ **WP9**: reporting JSONL (local strict writer)
- 🟡 **WP7**: semantic indexer (batch-first) — ongoing hardening + dedupe strategy
- ⏭️ **WP6 (next MUST)**: session restore + context builder consuming semantic artifacts (before new UI)
- ⏭️ **WP2**: new UI after WP6

### What we need feedback on
- Best UX for context control (user-driven “what are we doing now?” context selector).
- Minimal set of tools for browsing knowledge base without token waste.
- Dedupe strategy for semantic artifacts (source hashing vs. manifest compaction).

---

## Discussion 2 — OmniFlow Beta (Demo): how to access + what to try

**Demo URL:** https://omniflowbeta-gjv5gjhezwbfg7pb7pucwe.streamlit.app/

### What the demo is
Streamlit UI acting as a LAB console for the backend tool_call_handler.

### Recommended first tests
- Start a new session and set a distinct `user_id`.
- Run `list_blobs` and confirm you only see your namespace.
- Create a task in `TM.json` (add), then update it, then delete it.
- Upload a small note file and read it back.
- Use `read_many_blobs` to read multiple small files in one tool call.

### What to watch for
- Latency: tool_call_handler round-trip vs. UI overhead.
- Correct propagation of `X-User-Id` across all tool calls.
- Whether the agent ever tries to read ambiguous filenames (basename-only); it should resolve safely or ask.

### Known limitations (current)
- LAB UI only (not product UX).
- No OAuth yet (soft identity via `user_id`).
- WP6 context restore is the next step to enable richer, stable sessions.

