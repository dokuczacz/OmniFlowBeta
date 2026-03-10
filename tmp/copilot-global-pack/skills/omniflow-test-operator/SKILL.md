---
name: omniflow-test-operator
description: Focused testing and verification with smallest relevant scope and clear success signals.
---

# omniflow-test-operator

## When to apply
Use when user asks for tests or when changes may introduce regressions.

## Composition
- Mode: append.

## Output (MUST)
1. Test target (one sentence)
2. 1-3 commands max
3. One success signal line

## Rules
- Prefer one focused test over full suite.
- Do not claim confidence without output evidence.
- Avoid destructive commands.
- Keep logs minimal unless user asks.

## Stage scope
- Planning only: define acceptance checks.
- Local change: one nearest focused test.
- Milestone: focused tests + minimal smoke.
- CI failure: prioritize failing job subset.
