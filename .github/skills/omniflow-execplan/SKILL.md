---
name: omniflow-execplan
description: Maintain one per-task ExecPlan artifact under tmp for multi-step work with a quick bypass option.
---

# omniflow-execplan

## When to apply
Use when:
- task is multi-step (>3 steps), or
- user asks for plan/execplan/artifact, or
- unknown scope requires explicit sequencing.

Quick bypass:
- If user says `quick`, `szybko`, or `no plan`, do not create/update a plan file.
- Return only a concise delta summary and the smallest next action.

## Composition
- Default: append.
- If blocker is critical and missing artifacts prevent correctness, combine with stall handling pattern.

## Output (MUST)
For normal mode:
1. Create or update `tmp/<task>_execplan.md`.
2. Return file path and a short delta summary.
3. Keep one master ExecPlan per active task.

For quick bypass mode:
1. No file creation.
2. 3 bullets max: current state, decision, next action.

## Required sections for plan file
- Goal
- Inputs and Context
- Acceptance
- Plan
- Commands
- Validation
- Recovery
- Notes

## Rules
- Keep plan compact and updated as work progresses.
- No secrets in plan artifacts.
- Include DoD commands and thresholds in Acceptance.
