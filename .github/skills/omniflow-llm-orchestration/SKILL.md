---
name: omniflow-llm-orchestration
description: Deterministic backend-first LLM orchestration with JSON-only contracts and payload matrix tracking.
---

# omniflow-llm-orchestration

## When to apply
Use for orchestration topics:
- intention routing, phase/stage ownership, prompt contract,
- tool-loop behavior, payload shape, response observability.

## Composition
- Append mode.
- Use execplan for multi-step work.
- Route verification commands through test-focused workflow.

## Output (MUST)
Return all items:
1. Semantic vs deterministic split.
2. Orchestration contract delta.
3. Prompt/payload delta.
4. Payload matrix path status.
5. Verification commands and success signals.

## Artifact
- Maintain `tmp/<task>_openai_payload_matrix.md`.
- Include step -> input/prompt/tools/metadata/output schema.

## Rules
- Backend owns phase/stage and tool allowlists.
- JSON-only responses, including errors.
- Enforce bounded tool loops and explicit stop conditions.
- Required observability fields: `response_id`, `intent_response_id`, `prompt_id`, `thread_id`, `run_id`, `phase`, `stage`.
- No secrets or tokens in logs/artifacts.
