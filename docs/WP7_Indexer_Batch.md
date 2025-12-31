# WP7 — Semantic Post-Processing / Indexer (batch-first)

- Status: active
- Scope: offline semantics creation (queue → indexer → artifacts → manifest)
- Audience: operator + developer

## Goal (why WP7 exists)

- Keep `tool_call_handler` latency stable: semantics generation runs **outside** the request path.
- Persist **per-interaction semantic memory** so WP6 can build context without scanning raw logs.
- Keep payloads deterministic and bounded: no large tool outputs, append-only where possible.

## Pipeline overview (per user)

1. `save_interaction` produces a sanitized queue item (JSONL).
2. Indexer consumes queue items in batches:
   - Manual: `wp7_indexer_run` (HTTP trigger)
   - Automatic: `wp7_indexer_timer` (timer trigger)
3. For each interaction, WP7 writes:
   - a semantic artifact JSON
   - an append-only manifest line in `semantic/index.jsonl`
   - optionally an `uncategorized` portfolio entry (append-only)

## Storage contracts (source of truth)

All paths are under `users/{user_id}/...`:

- Queue (append-only JSONL): `interactions/indexer_queue.jsonl`
- Cursor/state: `interactions/indexer_state.json` (block blob JSON; includes `byte_offset`)
- Batch state (timer mode): `interactions/indexer_batch_state.json` (block blob JSON)
- Semantic artifacts: `interactions/semantic/{interaction_id}.json` (block blob JSON)
- Semantic manifest (append-only JSONL): `interactions/semantic/index.jsonl`
- Uncategorized portfolio (append-only JSONL): `interactions/portfolio/uncategorized.jsonl`
- Batch audit (append-only JSONL): `interactions/batch/audit.jsonl`

Code reference: `backend/shared/wp7_indexer.py`

## Input: queue item (what the indexer sees)

Producer: `backend/save_interaction/__init__.py`

Each queue line is one JSON object (example):

```json
{
  "schema_version": "omniflow.wp7.queue.v1",
  "interaction_id": "INT_20251229_005620_037456",
  "timestamp_utc": "2025-12-29T01:42:01.630835Z",
  "user_id": "MarioBros",
  "thread_id": "handle_...",
  "language": "mixed",
  "user_message": "…truncated…",
  "assistant_response": "…truncated…",
  "tools_used": ["list_blobs", "read_many_blobs"],
  "estimated_tokens": 420,
  "estimated_tokens_hi": 560
}
```

Invariants:

- Item is sanitized (bounded by env caps) and intentionally excludes tool outputs.
- `estimated_tokens` is deterministic and used only for batching thresholds.

## How semantics are created (Responses + strict schema)

WP7 uses the OpenAI **Responses** endpoint with a Dashboard prompt (`OPENAI_INDEXER_PROMPT_ID`).

- Sync mode: calls `openai_client.responses.create(...)` directly.
- Batch mode: timer submits a JSONL file to OpenAI Batches (`endpoint=/v1/responses`).

Output is constrained at request-time with a strict JSON schema:

- Code: `wp7_text_json_schema_format()` in `backend/shared/wp7_indexer.py`
- Expected shape: either `{"items":[...]}` (preferred) or `[...]` (fallback)

Each item must include:

- `interaction_id` (must match the queue item)
- `category` (enum)
- `summary` (short, stable)
- `tags[]` (stable kebab-case)
- `confidence` (0..1)
- `signal_level` (`low|medium|high`)

## Output: semantic artifact (per interaction)

Stored at: `users/{user_id}/interactions/semantic/{interaction_id}.json`

Minimal expected fields (example):

```json
{
  "schema_version": "omniflow.wp7.semantic.v1",
  "interaction_id": "INT_...",
  "user_id": "MarioBros",
  "timestamp_utc": "2025-12-29T01:42:01.630835Z",
  "category": "TM",
  "tags": ["task-management", "planning", "deadlines"],
  "summary": "Intent; Action(tool); Result (Scope).",
  "confidence": 0.82,
  "signal_level": "medium"
}
```

Notes:

- `signal_level` is either produced by the indexer or derived deterministically from `confidence`.
- `category` + `tags` are designed to be cheap inputs for WP6 selection and grouping.

## Output: semantic manifest line (index.jsonl)

Stored at: `users/{user_id}/interactions/semantic/index.jsonl` (append-only)

Purpose:

- WP6 reads this first to select a small set of high-signal artifacts without scanning raw logs.

## Uncategorized portfolio (review bucket)

WP7 appends a review entry to:

`users/{user_id}/interactions/portfolio/uncategorized.jsonl`

When:

- missing/invalid `category`, or
- `confidence < WP7_UNCATEGORIZED_CONFIDENCE_LT` (default `0.6`)

## Batching thresholds (defaults)

Defaults live in `backend/local.settings.template.json`.

- `WP7_TARGET_BATCH_TOKENS=1000`
- `WP7_HARD_MIN_BATCH_TOKENS=600`
- `WP7_MAX_WAIT_SECONDS=300`
- `WP7_MAX_ITEMS_PER_RUN=25`
- `WP7_MAX_OUTPUT_TOKENS_PER_ITEM=180`
- `WP7_ALLOWED_CATEGORIES=PE,UI,ML,LO,PS,TM,SYS,GEN,ID`
- `WP7_UNCATEGORIZED_CONFIDENCE_LT=0.6`

Batch rule:

- Submit when `tokens_sum >= TARGET`, or when `elapsed >= MAX_WAIT` and `tokens_sum >= HARD_MIN`.

## Acceptance (how to verify WP7 in an environment)

- Queue grows: `interactions/indexer_queue.jsonl` gains new lines after `save_interaction`.
- Artifacts appear: `interactions/semantic/INT_*.json` created for recent interactions.
- Manifest grows: `interactions/semantic/index.jsonl` gains new lines.
- State advances: `interactions/indexer_state.json` shows increasing `byte_offset`.

## Rollback / safe disable

- Set `WP7_ENABLED=0` (indexer stops running; producer enqueue may still be attempted).
- Optionally set `WP7_INDEXER_MODE=sync` to stop batch mode and rely on manual runs.

