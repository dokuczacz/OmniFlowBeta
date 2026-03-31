# Repo Cleanup + GitHub Polish ExecPlan

## Goal
Make OmniFlowBeta repository clean, visitor-friendly, and integration-ready on GitHub, including quasi-MCP documentation and governance files.

## Inputs and Context
- User requested: full repo cleanup + dead code/orphan review + GitHub updates.
- Scope: repo files + GitHub hygiene; cleanup mode balanced.
- Required addition: mention quasi-MCP integration and test model link.

## Acceptance
1. README clearly explains product, quasi-MCP, and test status.
2. Dedicated docs guide exists for quasi-MCP and connection flow.
3. `.github` governance baseline exists (templates/checklists/ownership/security).
4. Low-risk repo noise is archived/removed without breaking references.
5. `git status` clean after commit and key docs links resolve.

## Plan
1. Refresh README top-level narrative and links.
2. Add quasi-MCP guide in docs and link from README/docs index.
3. Add `.github` governance files: CODEOWNERS, issue templates, PR template, skills/instructions indexes, SECURITY.
4. Perform low-risk cleanup of superseded root docs.
5. Validate with searches + git diff + smoke checks.

## Commands
- `git status --short`
- `rg --files`
- `rg "<target phrase>"`
- `git diff --stat`

## Validation
- Verify README contains test-model link and test-version note.
- Verify docs index links to quasi-MCP guide.
- Verify templates and CODEOWNERS are present.
- Verify removed files are not referenced.

## Recovery
- If link/reference breaks, restore file from git and convert to archived pointer doc.
- If cleanup uncertain, move file under `docs/archived/` instead of delete.

## Notes
- Balanced mode: do not remove risky code paths without explicit call-site proof.
