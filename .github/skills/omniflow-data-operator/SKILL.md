---
name: omniflow-data-operator
description: Operator-friendly dataset pipeline runbook with background execution, progress snapshots, and sampling checks.
---

# omniflow-data-operator

## When to apply
Use for pipeline/batch execution, progress checks, ETA, and output sampling.

## Composition
- Append mode.
- If progress table skill is active, table comes first.

## Output (MUST)
1. One run command.
2. One monitor command.
3. One success signal line.

## Rules
- Prefer existing progress files over large storage scans.
- Keep commands short and copy/paste-ready.
- Use env vars for secrets.
- If no tests exist, suggest deterministic repro command.

## Example templates
```powershell
# Start in background
Start-Job -Name data-pipeline -ScriptBlock { Set-Location "<repo>"; <command> }

# Progress snapshot
powershell -ExecutionPolicy Bypass -File .\show_progress.ps1
```
