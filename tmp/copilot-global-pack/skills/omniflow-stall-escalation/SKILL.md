---
name: omniflow-stall-escalation
description: Detect stall/blockers and force a short split-or-escalate decision.
---

# omniflow-stall-escalation

## When to apply
Use if any occurs:
- missing inputs block correctness,
- two turns without measurable progress,
- scope exceeds smallest safe next step,
- contract details are missing and would require guessing.

## Composition
- Mode: replace.

## Output (MUST)
1. Blocker: one sentence
2. Option A - Split: 1-3 smallest next steps
3. Option B - Escalate: missing artifact/tool/access
4. Operator question: one direct question

## Rules
- No invented results.
- Prefer split if feasible with <= 3 files or commands.
- Keep concise.
