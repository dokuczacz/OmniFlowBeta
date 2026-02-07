# Dashboard Prompt Switch Checklist

Working directory: `C:\AI memory\NewHope\OmniFlowBeta`

## Goal
Safely switch runtime to PRO stateless prompt, pinned by ID and version.

## Step A - Dashboard update
1. Create/update prompt in OpenAI Dashboard with content from:
   - `docs/workflow/prompts/personal_assistance_pro_stateless.md`
2. Publish a new prompt version.
3. Record values:
   - `prompt_id`
   - `prompt_version`

## Step B - Environment pinning
Set app settings:
- `OPENAI_PROMPT_ID=<prompt_id>`
- `OPENAI_PROMPT_VERSION=<prompt_version>`
- `OPENAI_CONTEXT_BUILDER_PROMPT_ID=<existing_or_new_builder_prompt_id>`
- `OPENAI_CONTEXT_BUILDER_PROMPT_VERSION=<builder_prompt_version_if_used>`
- `WP6_RESPONSES_STATELESS=true` (recommended for full stateless flow)

## Step C - Runtime sanity checks
Run:
```powershell
python -c "from backend.shared.tool_handler_config import build_tool_handler_config as b; c=b(); print({'wp6_responses_stateless':c.wp6_responses_stateless,'wp7_indexer_mode':c.wp7_indexer_mode})"
```

Expected:
- `wp6_responses_stateless` is `True`
- no missing prompt ID vars

## Step D - Smoke tests (10 runs)
1. Normal query (`action=run`) returns user-facing text.
2. No manifest/config JSON leaks in response text.
3. Polling (`action=get_run_progress`) does not trigger model run side effects.
4. Complex recap query can route toward DEEP path.

## Step E - Rollback
If quality regresses:
1. Revert only:
   - `OPENAI_PROMPT_ID`
   - `OPENAI_PROMPT_VERSION`
2. Keep backend guardrails enabled.
