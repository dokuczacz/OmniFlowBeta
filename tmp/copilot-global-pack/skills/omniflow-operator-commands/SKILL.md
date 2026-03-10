---
name: omniflow-operator-commands
description: Provide operator-friendly, non-blocking run commands with monitoring and success signal.
---

# omniflow-operator-commands

## When to apply
Use when user asks for run commands, background execution, or monitoring commands.

## Composition
- Mode: append.

## Output (MUST)
- Copy/paste command block.
- One monitor snippet.
- One success signal line.

## Rules
- Prefer non-blocking patterns.
- No secrets inline.
- Keep command paths explicit.
- Keep output compact.

## Template
```powershell
Start-Job -Name <job> -ScriptBlock { Set-Location <workdir>; <command> }
Get-Job -Name <job>
Receive-Job -Name <job> -Keep
```
