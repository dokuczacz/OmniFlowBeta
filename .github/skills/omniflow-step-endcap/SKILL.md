---
name: omniflow-step-endcap
description: Append a strict 3-line endcap with target, done-now, and next actions.
---

# omniflow-step-endcap

## When to apply
Use after status updates, summaries, or completed implementation steps.

## Composition
- Append mode.
- Always last block in response.

## Output (MUST)
Append exactly 3 lines:
- WU target: <completion target>
- Done now: <what was completed>
- Next: <1-3 concrete actions>

## Rules
- Keep concise and concrete.
- Include artifacts or commands when available.
- No extra prose after endcap.
