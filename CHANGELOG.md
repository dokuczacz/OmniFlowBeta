# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and versioning is pragmatic (beta tags are allowed).

## Unreleased

### Added
- README: API quick peek + known limitations + star callout.

## v2.0.0-beta (Patch 2.0 baseline)

Patch 2.0 focuses on deterministic agent orchestration and semantic/context foundations:

- WP1: Responses runtime + deterministic tool loop (`POST /api/tool_call_handler`).
- WP6: context builder + cache reuse (note: `DEEP` not deterministically forceable end-to-end).
- WP7: semantic indexer (batch-first): queue -> batch -> semantic artifacts -> manifest index.
- WP2: Next.js UI (Streamlit remains legacy/LAB).
- WP9: local reporting writer under `docs/workflow/wp9_reporting/`.

Docs:

- Patch 2.0 status: `docs/PATCH_2_STATUS.md`
- WP7 semantics: `docs/WP7_Indexer_Batch.md`
- WP6 context builder: `docs/workflow/wp6_context_builder/README.md`

## v1.x (Patch 1.0 legacy baseline)

- Streamlit LAB UI + blob-first storage tools + single orchestrator endpoint.
- Kept as historical reference in `docs/OmniFlow_Project_Summary_and_Next_Steps.md`.

