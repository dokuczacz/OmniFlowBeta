# Goal
Provide a single matrix showing what payload is sent to OpenAI at each backend step, and whether each step is fully dict-based.

# Scope
- Backend paths relevant to current PA refactor:
  - `backend/tool_call_handler/__init__.py`
  - `backend/wp7_indexer_run/__init__.py`
  - `backend/wp7_indexer_timer/__init__.py`

# Matrix (current state)
| Step | Flow | Code path | OpenAI API call | Prompt field in request | Input field in request | Output contract | `store` | Metadata keys | Dict compliance |
|---|---|---|---|---|---|---|---|---|---|
| S1 | PA intention (nano, semantic-only) | `tool_call_handler._pa_run_intention_step` | `responses.create` | none (no `prompt.id`) | `input=<single concatenated string prompt>` | `text.format=json_schema` strict `pa_intention_min_v2` (`primary/alternatives/slots/signals`); backend normalizes and deterministically derives `required_tools/prefetch_plan/write_intent` | `true` | `purpose,user_id,thread_id,run_id,phase,stage` | `PARTIAL` (request kwargs dict yes, prompt body string) |
| S2 | PA context builder (deep capsule prompt) | `tool_call_handler._wp6_build_context_pack_from_prompt` | `responses.create` | `prompt={"id": OPENAI_CONTEXT_BUILDER_PROMPT_ID}` | `input=json.dumps(cb_input_dict)` | validated by `_wp6_validate_context_pack` (JSON object expected) | default (not set) | `user_id,thread_id,runtime=context_builder` | `PARTIAL` (prompt object dict yes, input serialized string) |
| S3 | Main PA run (iteration 0) | `tool_call_handler.run_responses` | `responses.create` | `prompt={"id": OPENAI_PROMPT_ID}` (+ optional `variables` dict) | `input=<user_message + semantic-only context capsule (+ composer blocks for PA function)>` | model output + tool loop extraction | default (not set) | `user_id,thread_id,runtime,phase,stage,recent_user_turns,intent_router?,composer_*?` | `PARTIAL` (prompt/tools/metadata dict, input string) |
| S4 | Main PA run (tool loop iteration >0) | `tool_call_handler.run_responses` | `responses.create` | same as S3 | `input=[{"type":"function_call_output","call_id":"...","output":"..."}]` | model output continues until no function calls | default (not set) | same as S3 | `PASS` (dict/list-based input items) |
| S5 | WP7 indexer (manual run) | `wp7_indexer_run._call_indexer_model` | `responses.create` | `prompt={"id": prompt_id}` | `input=<string from _create_indexer_input(items)>` | `text.format=json_schema` via `wp7_text_json_schema_format()` | `false` | `runtime=wp7_indexer` | `PARTIAL` (prompt dict yes, input string) |
| S6 | WP7 indexer (timer) | `wp7_indexer_timer._call_indexer_model` | `responses.create` | `prompt={"id": prompt_id}` | `input=<string from _create_indexer_input(items)>` | `text.format=json_schema` via `wp7_text_json_schema_format()` | `false` | `runtime=wp7_indexer_timer` | `PARTIAL` (prompt dict yes, input string) |

# Source pointers
- Intention schema + call + backend normalization: `backend/tool_call_handler/__init__.py`
- Main responses call kwargs + tool loop: `backend/tool_call_handler/__init__.py`
- Runtime selection (`responses|auto` only): `backend/tool_call_handler/__init__.py`
- Context builder prompt call: `backend/tool_call_handler/__init__.py`
- WP7 run call: `backend/wp7_indexer_run/__init__.py:217`
- WP7 timer call: `backend/wp7_indexer_timer/__init__.py:645`

# Dict policy check (requested)
## Current verdict
- Backend OpenAI request envelopes are dict-based.
- Not all prompt/input bodies are dict-based payloads.
- Main gap: S1/S2/S3/S5/S6 still use string input bodies.
- Assistants runtime is removed from active routing path (responses-only).

## Context capsule policy (locked)
- Capsule for model input is semantic-only.
- Forbidden keys in capsule payload:
  - `user_id`, `session_id`, `run_id`, `ts_utc`, `phase`, `stage`, `response_id`, `prompt_id`,
  - `requires_confirmation`, `write_intent`, `tool_budget`.
- Operational hints remain in backend/run metadata only.
- Intent-scoped snippets:
  - TM intent (`PA-01`) => TM snippet only,
  - Gmail intent (`PA-14`) => Gmail snippet only.
- Size policy for current rollout: no trim/no hard cap.
- Runtime routing policy:
  - `fast/deep` is deprecated as routing control.
  - Runtime path is forced to FAST; `fast/deep/auto` is stored only as metadata quality hint.

## Required to reach strict "dict-first prompts" policy
1. Intention call (S1): replace monolithic prompt string with structured input object (message + constraints + catalog sections) rendered deterministically.
2. Context builder and WP7 (S2/S5/S6): keep prompt id, move `input` from plain text serialization to structured input items envelope with fixed schema.
3. Main run iteration 0 (S3): wrap user message in structured input item envelope to align with dict-first policy.
4. Add contract tests that fail if any PA OpenAI call uses raw freeform prompt assembly without schema-bound envelope.

# Notes
- This matrix is operational truth for auditing payloads sent to OpenAI during PA refactor.
- Update this file together with any OpenAI call-shape change.
- Prompt composition SOT for TM/Gmail is backend dict composer (`prompt_registry/*`), not dashboard prompt body text.
