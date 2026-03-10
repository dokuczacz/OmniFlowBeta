---
name: gh-address-comments
description: Address open PR review comments using gh CLI with explicit user-selected thread handling.
---

# gh-address-comments

## When to apply
Use when user asks to handle PR review comments or issue discussion feedback.

## Auth prerequisite
- Ensure `gh` is authenticated.
- Run `gh auth login` once if needed.
- Verify with `gh auth status` before comment retrieval.

## Composition
- Append mode.

## Output (MUST)
1. Enumerated list of comments/threads.
2. Short fix summary for each thread.
3. Ask user which numbered threads to address.
4. Apply only selected fixes.

## Rules
- Do not apply unselected comment fixes.
- If auth fails, ask user to re-authenticate and retry.
