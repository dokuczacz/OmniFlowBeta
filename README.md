# OmniFlow Beta


## 🧪 Welcome, Test Pilots & Codebreakers!

This is **OmniFlow Beta**—a playground for multi-user AI agent backends, built for those who love to poke, prod, and push systems to their limits. If you’re the kind of person who reads the source before the docs, writes curl one-liners in your sleep, or gets a thrill from finding edge cases, you’re in the right place.

---

## Latest updates

- **Minimal public footprint** ? local tests, workflow plans, and emulator state are now ignored so the repo only exposes the essential backend/frontend code everyone needs to run and extend.
- **Safer tool call handler** ? the Azure Functions handler now reads the latest assistant message reliably, handles direct-save actions without forcing proxy config, and keeps tool argument normalization centralized.
- **Configurability & docs** ? added .env.example, eliminated hard-coded secrets, and documented Azure Function deployment in docs/shared/DEPLOYMENT.md so teams can publish the same version you just shipped.
- **Live Streamlit demo** ? the current build is live at https://omniflowbeta-gjv5gjhezwbfg7pb7pucwe.streamlit.app/ for instant eyeballing before spinning up local tooling.

---

## ⚡️ What’s Inside?

- **Simple User Management**: User isolation is enforced, but the logic is intentionally minimal—perfect for reviewers who want to suggest improvements or test boundaries.
- **Multi-User Data Isolation**: Each user’s data is locked in their own namespace—try to break it!
- **Azure Blob Storage, Python 3.11, and Azure Functions**: Modern, scalable, and ready for your abuse.
- **RESTful Endpoints**: All the CRUD you crave, with user context enforced everywhere.
- **Singleton Azure Client**: Because you hate memory leaks and so do we.
- **Streamlit UI Example**: Hack it, extend it, or replace it with your own.
- **Full Audit Logging**: Every tool call, every parameter, every result—logged for your forensic pleasure.
- **OpenAI-Ready**: Drop in your API key and go wild.

---

## 🧭 Planned: Multi-Agent & Vector Features

**Multi-Agent Environment (coming soon):**
- Timer-driven “agents” (Cleaner, Adherence Checker, Task Manager, Summarizer) will run as background routines, each with a focused job (data validation, drift detection, agenda building, summarization).
- All agents use only GET endpoints and minimal writes (reports), keeping costs and risk low. No source file rewriting.
- Each agent is a timer-triggered function, using the same user isolation and logging as the rest of the system.

**Vector Storage & Semantic Search:**
- Data pipeline to chunk existing blob docs (JSON/MD/TXT) with metadata.
- Embeddings generated via OpenAI or Azure Cognitive Search.
- Storage options: pgvector (Postgres), Azure Cognitive Search, or FAISS (dev).
- Endpoints: `semantic_search(query, top_k, filter)` and `context_pack(query)` for deduped, ranked, cited results.
- Index state tracked in vector_index_state.json (etag/last_modified per file).

**Advanced GET & Tag-Based Search:**
- Fast, pure GET endpoints: list_blobs, head_blob_exists, get_blob_meta, read_blob_file (with offset/length), search_blob_names, search_blob_content (regex), get_daily_context, summarize_blob.
- Tag-based search: `search_by_tags(tags, match, category)` with a JSON index refreshed daily; fallback to on-demand scan.
- All GET endpoints are side-effect free and optimized for speed (HEAD/range, file size limits for regex).

---

## 🏗️ Directory Map

```
OmniFlowBeta/
├── backend/      # All the Azure Functions magic
│   ├── shared/   # User, config, and blob client logic
│   ├── add_new_data/ ... (and more endpoints)
│   ├── tests/    # Pytest-ready, add your own!
│   └── function_app.py
├── frontend/     # Streamlit demo UI
├── docs/         # Architecture, plans, and more
└── README.md     # (You are here!)
```

---

## 🧑‍💻 How to Break It (Setup & Test)

1. **Install dependencies**:
	```bash
	pip install -r requirements.txt
	```
2. **Spin up Azurite (local Azure Storage)**:
	```bash
	azurite
	```
3. **Fire up the backend**:
	```bash
	func start
	```
4. **Hit the endpoints** (example):
	```bash
	curl -X POST http://localhost:7071/api/add_new_data \
	  -H "Content-Type: application/json" \
	  -H "X-User-Id: test_user_123" \
	  -d '{"target_blob_name":"tasks.json","new_entry":{"id":"1","text":"Test task"}}'
	```
5. **Try with multiple user IDs. Try weird user IDs. Try missing user IDs. Try huge payloads.**

---

## 🧩 API Endpoints (for your scripts & tools)

- `/api/add_new_data`
- `/api/list_blobs`
- `/api/read_blob_file`
- `/api/update_data_entry`
- `/api/remove_data_entry`
- `/api/upload_data_or_file`
- `/api/tool_call_handler`
- `/api/get_current_time`
- ...and more!

All endpoints require a user context via `X-User-Id` header or `user_id` param. Try to bypass it—we dare you.

---

## 🧠 What to Test & Review

- Can you break user isolation?
- Can you race the blob storage and cause chaos?
- Are the logs complete and tamper-proof?
- Is the API consistent, predictable, and fun to script against?
- Does the singleton pattern hold up under load?
- Is the code readable, testable, and hackable?
- How would you improve the user management logic?
- How would you extend the multi-agent or vector features?

---

## 🗺️ Roadmap & Planning

- [x] Multi-user isolation (namespacing, validation)
- [x] Core CRUD endpoints
- [x] Streamlit UI integration
- [ ] Advanced analytics endpoints
- [ ] Role-based access control
- [ ] Real-time collaboration
- [ ] More tests, more chaos

See [MASTER_PLAN.md](../MASTER_PLAN.md) and [NEXT_STEPS.md](../NEXT_STEPS.md) for the gory details.

---

## 🧪 Contribute, Critique, or Just Break Stuff

- Fork, PR, or open an Issue for bugs, ideas, or rants.
- Add tests, docs, or wild new features.
- Review the code and tell us what stinks.

---

## 📜 License

MIT. Do what you want, but don’t blame us if you break production.

---

## 🦾 For the Curious

OmniFlow Beta is a testbed for robust, secure, and fun multi-user AI agent backends. If you find a bug, a race, or a design flaw, you’re our hero.

---

### Ready to test, review, and break things? Jump in!

