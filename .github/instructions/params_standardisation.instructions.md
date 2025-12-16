---
applyTo: '*'
---

you are an implementation agent (gpt-4.1) for the OmniFlowBeta project. follow this instruction when modifying any file in this repository.

project context:
- project name: OmniFlowBeta
- backend: Azure Functions
- frontend: Streamlit UI
- you must understand and respect project documentation in:
  C:\AI memory\NewHope\OmniFlowBeta\docs\shared\
- always check docs/shared first to reflect actual project structure and purpose.
- do not change .docs\shared\readme.md unless specifically instructed to do so.

general integration rules:
- implement new features or bugfixes by modifying both backend and frontend as needed.
- ensure every backend API change is reflected in frontend and vice versa.
- when adding dependencies, update requirements.txt in backend and/or frontend accordingly.
- keep code modular, readable, and aligned with existing patterns.
- keep documentation up-to-date when you change API payloads, data structures, flows, or UI.

working method (PDCA):
- before executing any modifications, propose a working plan (small steps, each 10–20 minutes) with time-effort estimation per step and overall.
- confirm the plan with the user BEFORE executing.
- execute step-by-step and keep an execution log (files changed, commands run, test results).
- include testing in the implementation process; report “done” only after tests pass.
- if tests fail, return to implementation until tests pass. if the problem is bigger, report it and propose a new plan.

secrets & safety:
- never put secrets into test scripts or repository.
- if secrets are required, use mocks or environment variables and document how to set them separately.

============================================================
TODAY PRIORITIES (must be implemented with minimal complexity)
============================================================

1) DIRECT SAVE (FAST-TRACK) + LATENCY (SPEC + PERFORMANCE + MEASUREMENT)
goal:
- implement direct saving of each user interaction/data entry to Azure Blob Storage.
- saving happens automatically per interaction/data event (no extra UI “Save” button).
- optimize the flow for minimal latency (remove unnecessary hops, lightweight endpoints).
- measure and document latency improvements (before/after).

storage layout (strict):
- each user has a dedicated directory:
  users/{user_id}/
- each category is a dedicated JSON file:
  users/{user_id}/{category}.json
  examples: users/{user_id}/PE.json, users/{user_id}/TM.json

standardized parameter schema (mandatory for all direct-save endpoints):
- user_id
- target_blob_name   (recommended: category filename, e.g. "TM.json" or "PE.json")
- new_entry          (object or string; must be normalized before save)

behavior (functional requirements):
- if the target file does not exist: create it.
- store data as a JSON list of entries (append new_entry).
- enforce user isolation and path safety:
  no path traversal, no cross-user read/write.
- validate:
  missing user_id/target_blob_name/new_entry => 400
  invalid user_id / invalid blob path => 400
- log minimal telemetry for each save:
  user_id, function_name, target_blob_name, status, duration_ms (no secrets, no sensitive payload dumps).

performance requirements (latency):
- remove unnecessary proxy/agent hops in the direct-save path wherever possible.
- keep endpoints lightweight:
  minimal payload parsing, no redundant transformations, no extra blob calls.
- reuse connections/clients where possible (avoid per-request heavy initialization).
- reduce round-trips to blob:
  avoid unnecessary read-before-write when safe.
- measure request/response time:
  - capture at least avg and p95 (or best available)
  - report before/after and explain if bottleneck is external (e.g. platform latency).

documentation requirements:
- update project docs/status files with:
  - direct-save flow diagram (short)
  - parameter schema (canonical)
  - latency measurements and conclusions
  - best practices applied (connection reuse, reduced hops, payload minimization)

definition of done:
- direct-save works end-to-end (create + append + readback).
- data is always written to users/{user_id}/... only.
- tests prove isolation between two different users.
- measurable improvement OR clearly documented bottleneck (with evidence).

2) USER MANAGEMENT (MVP, no overengineering)
goal:
- provide basic user management features:
  list users, select user, create new user.
- on new user creation:
  initialize all category files with starter data using the script tested today.
- support “load data set”:
  allow loading starter/category templates from blob storage into the new user directory.

requirements:
- keep it minimal (no roles/permissions/auth redesign unless explicitly requested).
- onboarding flow must be documented so it can be integrated into UI and automation.

definition of done:
- create user => creates users/{user_id}/ and initializes all category files.
- UI can select active user and call endpoints with that context.
- “load data set” works and is tested.

============================================================
TESTING REQUIREMENTS (must match implemented behavior)
============================================================
- tests must cover:
  - direct-save create + append + readback
  - invalid params (missing fields, invalid user_id/path)
  - multi-user isolation (user A cannot access user B)
  - onboarding: new user initialization creates all category files
  - latency measurement hook/report generation (as applicable)
- avoid secrets in tests; use mocks/env and document setup steps separately.
- run relevant backend tests and at least a smoke path through UI calling the updated endpoints.

final reporting format (mandatory):
- PLAN (steps + time estimation + risks + test plan) -> get approval
- EXECUTION LOG (changes + commands + results)
- RESULTS (what works, what changed, latency measurements)
- NEXT (1–3 small follow-up steps)


follow these instructions strictly when working on any file in this repository.
follow implementation steps as described in the approved plan.