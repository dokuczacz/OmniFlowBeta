---
name: mail-agent-operations
description: Run the full Custom GPT regression path for the recent fixes across tasks, mail, preferences, calendar, and user_id sanitization.
argument-hint: "Use for Custom GPT regression checks across tasks, mail, preferences, calendar, and user isolation."
---

# Custom GPT Regression Operator

Use this skill when the goal is to exercise the full changed surface of the Custom GPT backend, not just one capability. This skill is designed to validate the fixes shipped in the `capability_exec` flow.

Trigger phrases used by operators: `test custom gpt`, `custom gpt regression`, `golden tests`, `test tasks and mail`, `test capability exec`.

## Scope Under Test

- `task.create`, `task.list`, `task.update`, `task.complete`, `task.delete`
- `mail.authorize`, `mail.accounts.list`, `mail.send`, `mail.reply`
- `memory.preferences.get`, `memory.preferences.update`
- `calendar.events.list`
- user-scoped sanitization for `user_id`

## Fixed Behaviors To Validate

1. `task.create` returns `task_index` and downstream task operations accept it.
2. `mail.authorize` accepts `force: true` and returns a fresh reauth payload.
3. `mail.send` and `mail.reply` accept `attachments` without immediate schema rejection.
4. `memory.preferences.update` reports `unknown_keys` instead of silently dropping them.
5. `calendar.events.list` accepts bare dates like `2026-03-31` by normalizing to RFC3339.
6. `user_id` values containing `/`, `\`, or `..` do not escape their namespace.

## Endpoint Contract

Send all requests to:

```text
POST /api/tool_call_handler?action=capability_exec
```

Canonical envelope:

```json
{
  "action": "capability_exec",
  "user_id": "test_regression_user",
  "params": {
    "capability": "task.create",
    "confirm": false,
    "arguments": {}
  }
}
```

## Regression Sequence

### 1. Task Flow

Create a task and confirm `task_index` exists and is an integer >= 1.

```json
{
  "action": "capability_exec",
  "user_id": "test_golden_tasks",
  "params": {
    "capability": "task.create",
    "confirm": false,
    "arguments": {
      "title": "Golden Test Task",
      "priority": "high"
    }
  }
}
```

Then validate:

- `task.list` returns a flat `tasks` array with `task_index` on every task
- `task.update` works with `task_index`
- `task.complete` marks the task complete
- `task.delete` returns `409 CONFIRMATION_REQUIRED` without `confirm: true`

### 2. Mail Auth And Attachments

Check OAuth bootstrap and forced reauth:

```json
{
  "action": "capability_exec",
  "user_id": "test_golden_mail",
  "params": {
    "capability": "mail.authorize",
    "confirm": false,
    "arguments": {
      "force": true
    }
  }
}
```

Validate:

- response includes `authorize_url`
- response includes `reauth_reason: "force"`
- `authorized` is false for a fresh test user

Then send an attachment-shaped payload to `mail.send` and `mail.reply`:

```json
{
  "action": "capability_exec",
  "user_id": "test_golden_mail",
  "params": {
    "capability": "mail.send",
    "confirm": true,
    "arguments": {
      "to": ["test@example.com"],
      "subject": "Golden Test with Attachment",
      "body": "Attachment validation",
      "attachments": [
        {
          "fileName": "test.txt",
          "contentBase64": "VGhpcyBpcyBhIHRlc3Qu"
        }
      ]
    }
  }
}
```

Expected outcome:

- auth failure is acceptable for a fresh user
- attachment shape failure is not acceptable
- missing-confirm failure must be `409 CONFIRMATION_REQUIRED`

### 3. Preferences Feedback

Use mixed valid and unknown keys:

```json
{
  "action": "capability_exec",
  "user_id": "test_golden_prefs",
  "params": {
    "capability": "memory.preferences.update",
    "confirm": false,
    "arguments": {
      "preferences": {
        "brevity": "medium",
        "fast_mode": true,
        "language": "en-US",
        "timezone": "UTC"
      }
    }
  }
}
```

Validate:

- response remains `success`
- `updated_keys` includes supported keys only
- `unknown_keys` includes `language` and `timezone`

### 4. Calendar Date Normalization

Call `calendar.events.list` using bare dates:

```json
{
  "action": "capability_exec",
  "user_id": "test_golden_prefs",
  "params": {
    "capability": "calendar.events.list",
    "confirm": false,
    "arguments": {
      "time_min": "2026-03-31",
      "time_max": "2026-04-07",
      "max_results": 10
    }
  }
}
```

Validate:

- no RFC3339 format complaint
- auth failure is acceptable
- date-format failure is not acceptable

### 5. Namespace Sanitization

Probe user isolation with malformed `user_id` values:

```json
{
  "action": "capability_exec",
  "user_id": "user/../../admin",
  "params": {
    "capability": "memory.preferences.get",
    "confirm": false,
    "arguments": {}
  }
}
```

Also test:

- `user..evil`
- `user\\nested`

Expected outcome:

- request may succeed or fail safely
- it must not escape namespace boundaries
- it must not produce traversal-specific backend errors

## Stop Conditions

The regression pass is complete when all of the following are true:

1. Tasks return and consume `task_index` correctly.
2. Mail auth supports forced reauth and attachment payloads are accepted structurally.
3. Preferences surface `unknown_keys`.
4. Calendar bare dates do not trigger RFC3339 validation errors.
5. Traversal-style `user_id` input is handled safely.

## Test Files

Use these files as the source of truth for payloads and assertions:

- `tests/e2e/test_custom_gpt_tasks_golden.py`
- `tests/e2e/test_custom_gpt_mail_oauth_golden.py`
- `tests/e2e/test_custom_gpt_prefs_calendar_security_golden.py`

## Output Format

Return a short execution summary with:

1. Passed scopes
2. Failed scopes
3. Any auth-blocked checks that were structurally valid
4. Exact failing capability and reason if a regression is found
