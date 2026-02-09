# Tool Handler 1 Refactor — Planning Summary

**Status**: ✅ Planning Complete - Awaiting Operator Approval  
**Date**: 2026-02-05  
**Branch**: copilot/vscode-ml9xu74x-ysdi

---

## 📋 Overview

This directory contains comprehensive planning documents for refactoring OmniFlowBeta's Tool Handler 1 (`backend/tool_call_handler/__init__.py`) based on best practices from **OmniFlowCentral** and **CV Generator** research.

---

## 📚 Planning Documents

### 1. IMPLEMENTATION_PLAN_UPDATED.md
**Purpose**: Complete implementation plan with phases and timelines

**Contents**:
- Executive summary of the refactor
- Analysis findings from all three sources
- 6-phase implementation plan (13-19 day estimate)
- Best practices to apply
- Risk mitigation strategies
- Success metrics

**Key Sections**:
- Phase 1: Registry & Contracts (Foundation)
- Phase 2: Dispatch Pipeline Refactor
- Phase 3: Datasearch Engine
- Phase 4: WP6 Enhancement
- Phase 5: WP7 Enhancement
- Phase 6: Documentation & Validation

---

### 2. docs/BEST_PRACTICES_REFERENCE.md
**Purpose**: Catalog of patterns extracted from analysis

**Contents**:
- Architecture patterns (Registry-driven, Modular services)
- Tool design patterns (Dataset search, Batch operations, User isolation)
- Prompting patterns (Persona, Structured output, Few-shot, Delimiters)
- Error handling (Error taxonomy, Trace IDs)
- Data access patterns (Preferences, Bounded reads)
- Testing patterns (Contract tests, Golden tests)
- Documentation standards

**Use Cases**:
- Reference during implementation
- Onboarding new developers
- Code review checklist
- AI agent instructions

---

### 3. docs/ARCHITECTURE_ANALYSIS.md
**Purpose**: Comparative analysis of the three systems

**Contents**:
- Side-by-side comparison of patterns
- OmniFlowBeta current state
- OmniFlowCentral reference implementation
- CV Generator best practices
- Implementation priorities
- Risk assessment
- Success metrics

**Key Comparisons**:
- Tool registration & dispatch
- Error handling
- Dataset search
- Prompting style
- User isolation
- Batching & performance

---

### 4. Original Planning Documents
- `tmp/tool_handler_1_execplan.md` - Initial execution plan
- `IMPLEMENTATION_PLAN_TOOL_HANDLER_1.md` - Original implementation plan

These provided the foundation for the updated plan.

---

## 🎯 Key Findings

### From OmniFlowCentral

**✅ Adopt These Patterns:**
1. **TOOL_SPECS** - Single source of truth for tool definitions
2. **TOOL_HANDLERS** - Clean dispatch table
3. **ToolError** - Structured error taxonomy
4. **Parameter normalization** - Canonical names and aliases
5. **User validation** - Strict format checking
6. **Dataset search** - Scan → Confirm → Fetch workflow

### From CV Generator Research

**✅ Apply These Practices:**
1. **Persona pattern** - Explicit role definition in prompts
2. **Structured output** - JSON schema enforcement
3. **Few-shot examples** - In-prompt demonstrations
4. **Section delimiters** - Clear markers ([CONTEXT], [MESSAGE])
5. **Negative constraints** - Explicit "DO NOT" rules
6. **Version control** - Track prompts like code

### From OmniFlowBeta Analysis

**✅ Preserve These Strengths:**
1. Sophisticated WP6/WP7 architecture
2. Excellent batch operations (read_many_blobs)
3. Strong user isolation
4. Preference-based access control
5. Semantic indexing with deduplication

**⚠️ Improve These Areas:**
1. Modularize 3500+ line god file
2. Centralize tool definitions
3. Standardize error handling
4. Add unified datasearch
5. Apply prompting best practices

---

## 📊 Current vs. Target State

### Current State
```
backend/tool_call_handler/__init__.py  (~3500 lines)
├── Ad-hoc tool validation
├── Scattered error handling
├── Embedded WP6/WP7 logic
├── No central registry
└── Difficult to test
```

### Target State
```
backend/tool_call_handler/
├── __init__.py              (~200 lines - thin orchestration)
├── dispatch.py              (~300 lines - pipeline)
├── handlers/                (tool implementations)
│   ├── blob_handlers.py
│   ├── data_handlers.py
│   └── search_handlers.py
├── wp6/                     (context builder)
│   ├── fast_context.py
│   ├── deep_context.py
│   ├── routing.py
│   └── cache.py
└── wp7/                     (semantic indexer)
    ├── batch.py
    └── dedup.py

backend/shared/
├── tool_specs.py            (TOOL_SPECS registry)
├── tool_registry.py         (registry functions)
└── error_codes.py           (ToolError + taxonomy)
```

---

## 🚀 Implementation Phases

### Phase 1: Registry & Contracts (2-3 days)
**Goal**: Single source of truth for tools

**Deliverables**:
- `backend/shared/tool_specs.py` - TOOL_SPECS dictionary
- `backend/shared/error_codes.py` - ToolError class + codes
- `backend/shared/tool_registry.py` - Registry functions
- Updated `AGENT_FUNCTIONS_CATALOG.json`
- Registry integrity tests

### Phase 2: Dispatch Refactor (3-4 days)
**Goal**: Clean, testable dispatch pipeline

**Deliverables**:
- `backend/tool_call_handler/dispatch.py` - Dispatch logic
- `backend/tool_call_handler/handlers/*` - Extracted handlers
- Refactored `__init__.py` (reduced size)
- Dispatch unit tests

### Phase 3: Datasearch Engine (2-3 days)
**Goal**: Unified, bounded search capability

**Deliverables**:
- `backend/tools/dataset_search.py` - Manifest search
- Cursor pagination support
- Datasearch tests
- Integration with WP6

### Phase 4: WP6 Enhancement (3-4 days)
**Goal**: Strict contracts, better caching

**Deliverables**:
- ContextPack v1 schema (pydantic)
- Modular WP6 structure (`wp6/` directory)
- Enhanced caching with intent keys
- WP6 contract tests

### Phase 5: WP7 Enhancement (2-3 days)
**Goal**: Batch-first, optimized caching

**Deliverables**:
- Verified batch-first semantics
- Prompt caching implementation
- Idempotency improvements
- WP7 tests

### Phase 6: Documentation (1-2 days)
**Goal**: Complete documentation

**Deliverables**:
- `docs/prompt_contract_checklist.md`
- `docs/tool_handler_contracts.md`
- Updated existing docs
- Migration guide

**Total Estimate**: 13-19 days (sequential)

---

## ✅ Success Criteria

### Code Quality
- [ ] Tool handler <1500 lines (down from 3500+)
- [ ] Test coverage >80%
- [ ] All tools in registry
- [ ] Zero ad-hoc validations
- [ ] Modular architecture

### Performance
- [ ] Search <1s for 1000+ items
- [ ] Prompt cache hit rate >80%
- [ ] API calls reduced >50%
- [ ] Batch processing >90%

### Developer Experience
- [ ] New tool in <30 minutes
- [ ] Clear error messages
- [ ] Comprehensive docs
- [ ] Easy local testing

### Reliability
- [ ] Zero silent failures
- [ ] All errors have codes
- [ ] Schema validation 100%
- [ ] No data loss on failures

---

## 🎓 Best Practices Applied

### Architecture
✅ Registry-driven design  
✅ Modular service layers  
✅ Parameter normalization pipeline  
✅ Clean separation of concerns  

### Tools
✅ Dataset search pattern (Scan → Confirm → Fetch)  
✅ Batch-first operations  
✅ Bounded operations (limits, pagination)  
✅ User isolation with validation  

### Prompting
✅ Persona pattern  
✅ Structured output with schemas  
✅ Few-shot examples  
✅ Section delimiters  
✅ Negative constraints  

### Error Handling
✅ Structured error taxonomy  
✅ ToolError exception class  
✅ Trace ID support  
✅ Actionable error messages  

### Testing
✅ Contract tests (behavior, not implementation)  
✅ Golden tests (reference outputs)  
✅ Integration tests  
✅ Unit tests for components  

---

## 📋 Next Steps

### Immediate (Before Implementation)
1. ✅ **Planning Complete**
2. ⏳ **Awaiting Operator Approval** of IMPLEMENTATION_PLAN_UPDATED.md
3. ⏳ **Confirm Git Strategy** (current branch is clean)

### Phase 1 Start (After Approval)
1. Create `backend/shared/tool_specs.py`
2. Create `backend/shared/error_codes.py`
3. Create `backend/shared/tool_registry.py`
4. Update `AGENT_FUNCTIONS_CATALOG.json`
5. Add registry tests

### Continuous
- Run tests after each change
- Review code before commits
- Update documentation as we go
- Measure performance impacts

---

## 📖 How to Use These Documents

### For Operators
1. Read `IMPLEMENTATION_PLAN_UPDATED.md` for full plan
2. Review `docs/ARCHITECTURE_ANALYSIS.md` for rationale
3. Approve plan to begin implementation

### For Developers
1. Use `docs/BEST_PRACTICES_REFERENCE.md` as coding reference
2. Follow patterns in `docs/ARCHITECTURE_ANALYSIS.md`
3. Implement phases from `IMPLEMENTATION_PLAN_UPDATED.md`

### For AI Agents
1. Load all three documents for context
2. Follow patterns from BEST_PRACTICES_REFERENCE
3. Use ARCHITECTURE_ANALYSIS for comparisons
4. Implement per IMPLEMENTATION_PLAN_UPDATED phases

---

## 🔗 External References

- **OmniFlowCentral**: https://github.com/dokuczacz/OmniFlowCentral
- **OpenAI Prompt Engineering**: https://platform.openai.com/docs/guides/prompting
- **Pydantic Documentation**: https://docs.pydantic.dev/
- **Azure Functions Python**: https://docs.microsoft.com/azure/azure-functions/functions-reference-python

---

## 📝 Change Log

### 2026-02-05
- ✅ Completed analysis of OmniFlowBeta, OmniFlowCentral, CV Generator patterns
- ✅ Created IMPLEMENTATION_PLAN_UPDATED.md (comprehensive refactor plan)
- ✅ Created BEST_PRACTICES_REFERENCE.md (pattern catalog)
- ✅ Created ARCHITECTURE_ANALYSIS.md (comparative analysis)
- ✅ Updated .gitignore to track these documents
- ⏳ Awaiting operator approval to begin Phase 1

---

**Status**: 🟡 Planning Complete - Ready for Implementation Approval

**Recommendation**: Review IMPLEMENTATION_PLAN_UPDATED.md and approve to begin Phase 1.

---

## 🧭 PA Semantic Prompting v1 (Stage/Phase) — Updated Plan

### Goal
Introduce semantic control for the Personal Assistant by passing `stage` and `phase` into the OpenAI Responses API (dashboard prompt variables), mirroring the CV-generator pattern.

### Recommended Stages (PA intents)
**Core**
- CALENDAR_QUERY
- CALENDAR_WRITE
- EMAIL_QUERY
- EMAIL_WRITE
- TASKS_MANAGE
- DAILY_PLAN
- NOTES_KB
- DECISION_SUPPORT

**Pro/Work**
- DOC_ANALYSIS
- REPORTING
- TRAVEL_PLANNING

**Optional (future)**
- CONTACTS_MANAGE
- FILES_MANAGE
- MEETING_SUMMARY

### Recommended Phases (action gate)
- DISCOVERY: clarify intent + missing data
- PLAN: draft actions, no external mutations
- CONFIRM: show exact actions, request approval
- EXECUTE: run tools/mutations/sends
- REPORT: results + optional trace/save

---

### Iteration 1 — Foundation (no architecture refactor)
1) **Responses API payload**
   - Add `prompt.variables = { stage, phase }`.
2) **Inline Intent Router**
   - Lightweight classifier returning top-k intents, `recommended_stage`, `recommended_phase`, `need_clarification`, and `clarify_questions`.
3) **Logging**
   - Log stage/phase in traces.

**DoD**
- Request includes variables.
- Stage/phase visible in logs.
- Dashboard prompt reacts to stage/phase (manual smoke test).

### Iteration 2 — Gating & Safety
1) Enforce PLAN → CONFIRM → EXECUTE for `*_WRITE`.
2) Add “what will happen” summary in CONFIRM.
3) Deny list of mutating actions in PLAN/CONFIRM.

**DoD**
- No mutating tools in PLAN/CONFIRM.
- EMAIL_WRITE / CALENDAR_WRITE never execute without CONFIRM.

### Iteration 3 — Logging for ML (WP6)
1) Log: user_text, top_intents + p, final stage/phase, confirmation flag.
2) Export JSONL dataset to storage.

**DoD**
- Dataset grows automatically.
- Ready for future intent model training.

---

### Test Plan
**Unit**
- Responses API payload contains `prompt.variables` (stage/phase).
- Intent Router JSON contract validation.
- Gating test: `*_WRITE` cannot reach EXECUTE without CONFIRM.

**Integration/E2E**
1) “Zaplanuj mój dzień” → DAILY_PLAN → PLAN → CONFIRM → EXECUTE.
2) “Napisz maila do X” → EMAIL_WRITE → PLAN → CONFIRM → EXECUTE.

**UI (pre-req)**
- RTL tests for PromptInput: render + typing + submit enabled/disabled.
- RTL tests for ModelSelector (via multimodal input): model change updates state.
