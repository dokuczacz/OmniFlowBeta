---
name: omniflow-github-operator
description: Safe Git and GitHub operator commands for inspect-stage-commit-push workflow.
---

# omniflow-github-operator

## When to apply
Use for commit/push/PR readiness and end-of-work-unit git hygiene.

## Composition
- Append mode.
- Keep output command-oriented.

## Output (MUST)
1. Inspect commands.
2. Explicit staging command.
3. Commit/push commands if requested.
4. One-line success signal.

## Rules
- Never remove local settings files.
- Never run destructive cleanup commands.
- Prefer explicit file staging over global staging.
- Suggest focused tests before commit when relevant.

## Templates
```powershell
git status -sb
git diff --stat
git add -- <file1> <file2>
git commit -m "<message>"
git push
```
