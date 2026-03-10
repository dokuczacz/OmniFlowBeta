# OmniFlow Copilot Baseline

Keep this file intentionally small. Domain workflows live in repo skills under `.github/skills/`.

## Authority and conflict handling
- Repo skill `SKILL.md` instructions win over this baseline when both apply.
- If two skills conflict, prefer the one with narrower scope and explicit output contract.
- Use `replace` behavior only for critical blocker handling.

## Always-on behavior
- Evidence-first: do not claim results without command output, logs, or file evidence.
- Smallest-next-step: prefer the minimal safe step that advances the current task.
- No secrets inline: use env vars and redact sensitive values in examples.
- Keep responses compact and actionable.

## Workflow defaults
- Use planning gate rules before non-trivial implementation.
- Prefer repo skills for orchestration, data pipeline, Blob ops, and GitHub flows.
- If user asks for quick mode (`quick`, `szybko`, `no plan`), skip heavy planning artifacts and provide a concise delta response.
