# OmniFlow Beta

OmniFlow Beta is a **multi-user AI agent backend** built on **Azure Functions + Azure Blob Storage**, with a **Next.js UI**.

## 🚀 Major Refactor In Progress

**Tool Handler Modernization** - Transforming 4165-line monolith into registry-driven architecture

- ✅ **Phase 1 Complete**: Registry & Contracts (112 tests passing)
- 🚧 **Phase 2 In Progress**: Dispatch Pipeline (18 tests passing)
- 📊 **Status**: [REFACTOR_STATUS.md](REFACTOR_STATUS.md)
- 📋 **Plan**: [IMPLEMENTATION_PLAN_UPDATED.md](IMPLEMENTATION_PLAN_UPDATED.md)

### Phase 1 Achievements
- ✅ Single source of truth (TOOL_SPECS registry)
- ✅ Structured error handling (ToolError with codes)
- ✅ Parameter aliasing (backward compatibility)
- ✅ Security field filtering
- ✅ 130 tests passing

## 📜 Privacy policy
- [Privacy policy](docs/shared/PRIVACY_POLICY.md)

---

## Key features (start here)

- **Multi-user isolation** via `X-User-Id` header (`users/{user_id}/...` namespace in Blob).
- **Deterministic tool orchestration** via `POST /api/tool_call_handler` (Responses tool-loop).
- **Storage tools**: list/read/update/delete/upload + `read_many_blobs` (batch multi-read).
- **Semantic pipeline (WP7)**: queue -> batch -> per-interaction semantic JSON artifacts -> manifest `index` (consumed by WP6).
- **Hybrid context routing (WP6)**: FAST by default; DEEP available but **not always forceable deterministically** end-to-end.

---

## API quick peek

- `POST /api/tool_call_handler` - main orchestrator (Responses tool-loop)
- `POST /api/read_many_blobs` - batch read (preferred over many single reads)
- `POST /api/save_interaction` - raw interaction log (feeds WP7)

---

## Current status (Patch 2.0)

Task / Work Package | Status
---|---
WP1 (Responses + dual runtime) | OK (Responses default)
WP7 (Semantic indexer, batch-first) | OK (queue -> batch -> artifacts -> index)
WP6 (Context builder + cache) | OK (note: e2e cannot deterministically force `DEEP`)
WP2 (Next UI) | OK (Streamlit is legacy)
WP9 (Reporting) | Available (local JSONL writer under `docs/workflow/wp9_reporting/`)

Legend: OK  X  Pending  Available/Needs constraints

---

## 📁 Project Structure

```
OmniFlowBeta/
├── backend/              # Azure Functions (legacy, deprecated)
├── OmniFlowCentral/      # Azure Functions (App2, active deployment)
├── ai-chatbot/           # Main UI (Next.js, actively maintained)
├── frontend/             # Lab UI (Streamlit, for testing)
├── data/                 # Local data files (gitignored)
├── docs/                 # Documentation (selective tracking)
├── experiments/          # Experimental features (untracked)
├── external/             # External templates/dependencies
├── logs/                 # Runtime logs (gitignored)
├── scripts/              # Automation scripts
├── tests/                # Test suites
├── tools/                # Local tooling (gitignored)
├── ui_archived/          # Archived UI proposals (gitignored)
│   ├── ui_next_proposal/ # Future Next.js UI proposal
│   └── ui_shiny/         # Archived Shiny UI
└── .azurite/             # Azurite emulator data (gitignored)
```

---

## Known limitations

## Live demo

- WP6: `DEEP` not deterministically forceable end-to-end.
- Streamlit UI is legacy/LAB only (primary UI is Next.js).

---

## Repo layout

```
OmniFlowBeta/
  backend/      # Azure Functions (this folder is the function app root)
  ui_next/      # Next.js UI (primary)
  ai-chatbot/   # Next.js AI chat template (reference)
  frontend/     # Streamlit UI (legacy LAB console)
  docs/         # Documentation (source of truth)
  scripts/      # Local helpers (ignored by default)
```

---

## Local run (recommended)

1) Backend deps: `pip install -r backend/requirements.txt`
2) Start Azurite (optional for local storage): `azurite`
3) Start Functions: `cd backend && func start`
4) Start Next UI: `cd ui_next && npm install && npm run dev`
5) (Optional) Start Streamlit UI: `cd frontend && streamlit run app.py`

### WP7 semantic batch helper

Run `scripts/run_wp7_semantic_batch.ps1` (PowerShell) or `scripts/run_wp7_semantic_batch.py` (straight Python) to launch `tools/wp7_semantic_batch.py` asynchronously. Both scripts forward any extra flags (e.g., `--source`, `--chunks`, `--reasoning`) to the Python helper so your terminal stays free while extracting schema-ready WP7 packs.
`tools/wp7_semantic_batch.py` also accepts:
  - `--interactive` to adjust the source/chunk/model/config interactively before each job.
  - `--debug` to turn on verbose logging (timestamps + DEBUG output).
  - `--loop`/`--loop-interval` to keep processing batches until a stop flag is detected; pair it with `--stop-after-next-batch` (or invoke the script with that flag alone) to request the loop shuts down after its next completed run.
To process the entire `Sesje/` archive in order, run `python scripts/wp7_batch/run.py`. The script walks every `.txt` in `C:\Users\Mariusz\OneDrive\Pulpit\ChatGPT\Historia\Sesje`, feeds each through `tools/wp7_semantic_batch.py` (two 5k chunks, schema output), and stores manifests/results under `data/wp7_batch/`. Add `--input-dir`, `--output-dir`, `--chunk-size`, `--chunks`, or `--max-output-tokens` if you need to override the defaults; use `--dry-run` for a preview. Use `--start-index` to resume from a specific transcript if you stopped earlier.

If this saved you time, star the repo.

---

## Docs

- Doc index: `docs/README.md`
- Patch 2.0 status: `docs/PATCH_2_STATUS.md`
- Semantics (WP7): `docs/WP7_Indexer_Batch.md`
- Context Builder (WP6): `docs/workflow/wp6_context_builder/README.md`
- Deployment: `docs/shared/DEPLOYMENT.md`
- Tool usage playbook: `FUNCTION_CALLS_PLAYBOOK.md`
- Changelog: `CHANGELOG.md`

---

## License

MIT.

