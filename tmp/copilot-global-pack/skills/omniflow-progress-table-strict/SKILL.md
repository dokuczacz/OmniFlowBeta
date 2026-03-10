---
name: omniflow-progress-table-strict
description: Strict progress table with verified numbers only and source attribution per row.
---

# omniflow-progress-table-strict

## When to apply
Use for status/progress/counts/completion reporting.

## Composition
- Mode: append.

## Output (MUST)
Provide exactly one table with columns:
Workstream/Task | Done/Total | Progress | Status | Source

## Rules
- No placeholders.
- No guessed totals.
- If unknown, use N/A and explain in Source.
- Use 3-7 rows for current scope only.

## Percent rule
- Progress = round(100 * done / total)
- If total unknown or zero, set N/A (baseline)
