---
name: gh-fix-ci
description: Inspect GitHub PR checks, fetch failing Actions logs, summarize root cause, then propose a fix plan.
---

# gh-fix-ci

## When to apply
Use when user asks to debug or fix failing GitHub PR CI checks.

## Auth prerequisite
- Ensure `gh` is authenticated.
- Run `gh auth login` once if needed.
- Verify with `gh auth status` before check/log commands.

## Composition
- Append mode.
- Plan first, then implementation after user approval.

## Output (MUST)
1. Failing checks summary.
2. Relevant log snippet or missing-log note.
3. Fix plan for user approval.
4. Recheck commands.

## Rules
- Scope to GitHub Actions checks; report external providers as out-of-scope links.
- Avoid guessing root cause without logs.

## Commands
```powershell
gh pr view --json number,url
gh pr checks <pr> --json name,state,link,startedAt,completedAt
gh run view <run_id> --json name,workflowName,conclusion,status,url
gh run view <run_id> --log
```
