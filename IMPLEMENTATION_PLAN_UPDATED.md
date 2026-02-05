# OmniFlowBeta Tool Handler 1 — Updated Implementation Plan

**Status**: Ready for Implementation  
**Version**: 2.0 (Enhanced with best practices from OmniFlowCentral and CV Generator patterns)  
**Last Updated**: 2026-02-05  
**Owner**: Operator + AI Agent

---

## Executive Summary

This plan refactors OmniFlowBeta's Tool Handler 1 (`backend/tool_call_handler/__init__.py`) into a **registry-driven, maintainable architecture** with clear contracts, bounded datasearch, and enhanced WP6/WP7 behavior. The refactor applies proven patterns from **OmniFlowCentral** and industry best practices from **CV generator prompting research**.

### Key Improvements
1. **Unified Tool Registry** - Single source of truth for tool definitions (inspired by Central's TOOL_SPECS)
2. **Deterministic Dispatch** - Clean pipeline: canonicalize → validate → execute → normalize
3. **Bounded Datasearch** - Manifest-based search with strict limits and pagination
4. **Enhanced WP6/WP7** - Batch-first processing, prompt caching, strict schemas
5. **Better Error Handling** - Structured error taxonomy and tracing

---

## Analysis Findings

### Current OmniFlowBeta Architecture

**Strengths:**
- Sophisticated dual-dispatch system (in-process + proxy fallback)
- WP6 context building with FAST/DEEP routing
- WP7 semantic indexing with deduplication
- Preference-based access control
- State management through handles and caches

**Pain Points:**
- ~3500+ line "god file" (`tool_call_handler/__init__.py`)
- Ad-hoc tool validation scattered throughout
- Inconsistent error handling patterns
- No single source of truth for tool definitions
- Limited test coverage for contracts

### Best Practices from OmniFlowCentral

**Key Patterns to Adopt:**

1. **TOOL_SPECS Registry Pattern**
```python
TOOL_SPECS = {
    "tool_name": {
        "description": "...",
        "params": {
            "param_name": {"type": "str", "required": True, ...}
        },
        "aliases": {"old_name": "new_name"}
    }
}
```

2. **TOOL_HANDLERS Dispatch Table**
```python
TOOL_HANDLERS = {
    "canonical_name": _handle_function
}
```

3. **Clean Parameter Normalization**
```python
def _normalize_tool_and_params(contract: dict) -> tuple[str, dict]:
    canonical = canonical_tool_name(raw_tool)
    params = apply_param_aliases(canonical, params)
    return canonical, params
```

4. **Structured Error Responses**
```python
class ToolError(Exception):
    def __init__(self, code, message, details=None, status=None):
        self.code = code  # MISSING_PARAM, VALIDATION_FAILED, etc.
        self.message = message
        self.details = details
        self.status = status
```

5. **Standard Response Envelopes**
```python
# Success
{"status": "success", "tool": "...", "user_id": "...", "result": {...}, "trace_id": "..."}

# Error
{"status": "error", "code": "...", "message": "...", "details": {...}, "trace_id": "..."}
```

6. **User Validation and Isolation**
- Strict user_id validation
- Consistent namespace enforcement
- Clear separation of system vs user data

### Best Practices from CV Generator Research

**Prompting Style Patterns:**

1. **Persona Pattern** - Explicit role definition
```
"Act as a context builder analyzing user interaction history..."
```

2. **Structured Output Pattern** - Enforce JSON schemas
```python
# Use strict JSON schema validation
# Prefer pydantic models over dict validation
# Generate JSON schema from dataclasses
```

3. **Few-Shot Pattern** - Provide examples in prompts
```
"Example 1: [input] -> [output]
Example 2: [input] -> [output]
Now process: [actual input]"
```

4. **Clear Delimiters** - Section markers
```
"[FAST_CONTEXT]
...context data...

[USER_MESSAGE]
...user input..."
```

5. **Negative Constraints** - Specify what to avoid
```
"Do NOT include personal information.
Do NOT perform full blob scans.
ALWAYS respect token budgets."
```

6. **Versioning** - Schema version in all outputs
```json
{
  "schema_version": "omniflow.context_pack.v1",
  ...
}
```

**Documentation Patterns:**
- Maintain prompt templates in version control
- Document prompt parameters explicitly
- Use examples for every tool/endpoint
- Specify common pitfalls and gotchas

---

## Implementation Plan

### Phase 1: Unified Registry & Contracts

**Goal**: Create single source of truth for tool definitions

**Tasks:**
1. Create `backend/shared/tool_specs.py`:
   - Define TOOL_SPECS dictionary (all tools)
   - Include params, types, required fields, aliases
   - Add descriptions and examples
   - Document gotchas and constraints

2. Create `backend/shared/error_codes.py`:
   - Define standard error codes:
     - `MISSING_PARAM` - Required parameter not provided
     - `VALIDATION_FAILED` - Parameter validation error
     - `INVALID_TOOL` - Tool not found in registry
     - `UPSTREAM_ERROR` - External service failure
     - `PREFERENCES_BLOCKED` - User preferences deny access
     - `AUTHORIZATION_FAILED` - Permission denied
     - `RATE_LIMITED` - Too many requests
     - `TIMEOUT` - Operation timeout
     - `SCHEMA_VIOLATION` - Output schema mismatch
   - Add `ToolError` exception class
   - Add `build_error_payload()` helper

3. Create `backend/shared/tool_registry.py`:
   - `canonical_tool_name(raw_name)` function
   - `apply_param_aliases(tool, params)` function
   - `validate_tool_params(tool, params)` function
   - `get_allowed_fields(tool)` function

4. Update `AGENT_FUNCTIONS_CATALOG.json`:
   - Align with TOOL_SPECS
   - Add structured examples
   - Document common pitfalls
   - Include best practices

**Acceptance:**
- ✓ All existing tools defined in TOOL_SPECS
- ✓ Registry loads successfully on startup
- ✓ Unit tests for registry functions pass
- ✓ No behavior changes to existing tools

---

### Phase 2: Dispatch Pipeline Refactor

**Goal**: Implement deterministic, testable dispatch

**Tasks:**
1. Create `backend/tool_call_handler/dispatch.py`:
   ```python
   def dispatch_tool_call(tool_name: str, params: dict, user_id: str, context: dict) -> dict:
       # 1. Canonicalize tool name
       # 2. Apply parameter aliases
       # 3. Validate required params
       # 4. Filter to allowed fields
       # 5. Execute handler
       # 6. Normalize result envelope
       # 7. Handle errors consistently
   ```

2. Refactor `backend/tool_call_handler/__init__.py`:
   - Extract dispatch logic to dispatch.py
   - Keep only orchestration/loop logic
   - Reduce file size by ~50%
   - Maintain backward compatibility

3. Create handler modules:
   - `backend/tool_call_handler/handlers/` directory
   - One module per tool category:
     - `blob_handlers.py` - read_blob, list_blobs, etc.
     - `data_handlers.py` - add_new_data, update_data_entry, etc.
     - `search_handlers.py` - get_filtered_data, dataset_search
     - `file_handlers.py` - upload, manage_files

4. Add tests:
   - `tests/unit/test_tool_registry.py`
   - `tests/unit/test_dispatch.py`
   - `tests/integration/test_tool_handlers.py`

**Acceptance:**
- ✓ All tools route through dispatch pipeline
- ✓ Existing tests still pass
- ✓ New unit tests cover dispatch logic
- ✓ Code maintainability improved (smaller modules)

---

### Phase 3: Datasearch Engine

**Goal**: Implement bounded, efficient dataset search

**Tasks:**
1. Create `backend/tools/dataset_search.py`:
   - Implement manifest-based search
   - Support filters: q, tags_any, tags_all, category, since, until
   - Implement cursor pagination
   - Add stable sorting (updated_at desc, blob_name asc)
   - Respect hard limits on results

2. Add to TOOL_SPECS:
   ```python
   "dataset_search": {
       "description": "Search user datasets using manifest",
       "params": {
           "q": {"type": "str", "required": False},
           "tags_any": {"type": "list", "required": False},
           "tags_all": {"type": "list", "required": False},
           "category": {"type": "str", "required": False},
           "since": {"type": "str", "required": False},  # ISO8601
           "until": {"type": "str", "required": False},  # ISO8601
           "limit": {"type": "int", "required": False, "default": 20, "max": 100},
           "cursor": {"type": "str", "required": False},
           "include_snippets": {"type": "bool", "required": False, "default": True},
           "fetch_content": {"type": "bool", "required": False, "default": False}
       }
   }
   ```

3. Optional semantic augmentation:
   - If WP7 index exists, search it for additional recall
   - Apply strict limits (no full scans)
   - Bounded tail reads only

4. Add tests:
   - Empty manifest handling
   - Filter combinations
   - Pagination correctness
   - Sort stability
   - Limit enforcement

**Acceptance:**
- ✓ Searches complete in <1s for 1000+ items
- ✓ No full blob reads without fetch_content=true
- ✓ Pagination is stable and deterministic
- ✓ Tests cover edge cases

---

### Phase 4: WP6 Enhancement

**Goal**: Strict contracts, better caching, clearer routing

**Tasks:**
1. Define ContextPack schema (pydantic model):
   ```python
   class ContextPackV1(BaseModel):
       schema_version: str = "omniflow.context_pack.v1"
       run_id: str
       correlation_id: Optional[str]
       mode: Literal["FAST", "DEEP"]
       budgets: Dict[str, int]  # token, byte limits
       layers: Dict[str, Any]   # L0-L3
       preferences: Dict[str, Any]
       created_utc: str
       pack_tokens_est: int
   ```

2. Refactor WP6 functions:
   - Extract to `backend/tool_call_handler/wp6/`:
     - `fast_context.py` - FAST mode logic
     - `deep_context.py` - DEEP mode logic
     - `routing.py` - Mode selection
     - `cache.py` - Context pack caching
     - `preferences.py` - Preference enforcement

3. Implement strict validation:
   - Validate all ContextPack outputs
   - Return VALIDATION_FAILED on schema errors
   - No silent fallbacks

4. Enhance caching:
   - Intent-based cache keys
   - TTL enforcement
   - Cache hit/miss metrics

5. Add tests:
   - Schema compliance tests
   - Budget enforcement tests
   - Routing determinism tests
   - Cache behavior tests

**Acceptance:**
- ✓ All ContextPacks are schema-valid
- ✓ FAST mode respects budgets
- ✓ DEEP escalation is deterministic
- ✓ Cache reduces API calls by >50%

---

### Phase 5: WP7 Enhancement

**Goal**: Batch-first processing, prompt caching optimization

**Tasks:**
1. Ensure batch-first semantics:
   - All WP7 paths use batching
   - No single-item "normal call" path
   - Consistent batch size logic

2. Implement prompt caching best practices:
   ```python
   # Stable prompt prefix (cache hits)
   system_prefix = """You are a semantic indexer...
   [Static instructions that rarely change]
   """
   
   # Consistent tool list (cache hits)
   tools = sorted(get_tool_list())  # Stable order
   
   # Cache key generation
   prompt_cache_key = hash(system_prefix + str(tools))
   ```

3. Add idempotency:
   - Unique dedup_key per interaction
   - Skip re-indexing existing items
   - Atomic writes to index.jsonl

4. Optimize batch processing:
   - Dynamic batch sizing based on token budget
   - Respect WP7_TARGET_BATCH_TOKENS
   - Avoid tiny batches (min threshold)

5. Add tests:
   - Batch behavior tests
   - Idempotency tests
   - Cache key stability tests
   - Dedup logic tests

**Acceptance:**
- ✓ No single-item indexing paths
- ✓ Prompt cache hit rate >80%
- ✓ Duplicate items are skipped
- ✓ Batch size is optimal

---

### Phase 6: Documentation & Contracts

**Goal**: Clear contracts for all stakeholders

**Tasks:**
1. Create `docs/prompt_contract_checklist.md`:
   - Required dashboard prompt settings
   - Variable placeholders documentation
   - Hard constraints that live in prompts
   - Testing checklist

2. Create `docs/tool_handler_contracts.md`:
   - Tool request/response schemas
   - Error codes and meanings
   - Rate limits and timeouts
   - User isolation guarantees

3. Update existing docs:
   - `AGENT_FUNCTIONS_CATALOG.json` - Add examples
   - `README.md` - Update architecture section
   - `docs/workflow/wp6_context_builder/README.md` - New contracts
   - `docs/WP7_Indexer_Batch.md` - Batch-first semantics

4. Create migration guide:
   - Breaking changes (if any)
   - Deprecation timeline
   - Upgrade instructions

**Acceptance:**
- ✓ All contracts documented
- ✓ Examples for every tool
- ✓ Prompts have clear requirements
- ✓ Migration path is clear

---

## Best Practices Applied

### From OmniFlowCentral

✓ **Registry-Driven Architecture**
- TOOL_SPECS as single source of truth
- TOOL_HANDLERS dispatch table
- Clean separation of concerns

✓ **Parameter Normalization**
- Canonical tool names
- Alias resolution
- Field filtering

✓ **Error Handling**
- Structured error codes
- ToolError exception class
- Consistent error payloads

✓ **User Isolation**
- Strict user_id validation
- Namespace enforcement
- Security boundaries

### From CV Generator Research

✓ **Prompting Patterns**
- Persona pattern for context builder
- Structured output with schemas
- Few-shot examples in prompts
- Clear section delimiters
- Negative constraints

✓ **Documentation**
- Version-controlled prompts
- Explicit parameter docs
- Examples for every operation
- Common pitfalls documented

### General Software Engineering

✓ **Type Safety**
- Pydantic models for schemas
- Type hints throughout
- Runtime validation

✓ **Testability**
- Small, focused modules
- Pure functions where possible
- Contract tests first
- Integration tests for flows

✓ **Maintainability**
- Explicit over implicit
- No silent fallbacks
- Structured logging
- Clear error messages

✓ **Performance**
- Batch operations default
- Caching where appropriate
- Bounded operations
- No full scans

---

## Risk Mitigation

### Risk: Breaking Changes
**Mitigation:**
- Phase implementation (incremental)
- Maintain backward compatibility during migration
- Comprehensive test coverage
- Gradual rollout with feature flags

### Risk: Prompt Drift
**Mitigation:**
- Prompt contract checklist
- Schema validation in code
- Version tracking in outputs
- Monitoring and alerts

### Risk: Performance Regression
**Mitigation:**
- Benchmark critical paths
- Monitor API call counts
- Cache hit rate tracking
- Batch size optimization

### Risk: Migration Complexity
**Mitigation:**
- Clear migration guide
- Tool-by-tool migration
- Rollback plan per phase
- Stakeholder communication

---

## Success Metrics

### Code Quality
- [ ] Tool handler <1500 lines (down from 3500+)
- [ ] Test coverage >80%
- [ ] All tools in registry
- [ ] Zero ad-hoc validations

### Performance
- [ ] Search <1s for 1000+ items
- [ ] Prompt cache hit rate >80%
- [ ] API calls reduced by >50% (caching)
- [ ] Batch processing >90% of items

### Reliability
- [ ] Zero silent failures
- [ ] All errors have codes
- [ ] Schema validation 100%
- [ ] No data loss on failures

### Developer Experience
- [ ] Clear error messages
- [ ] Comprehensive docs
- [ ] Easy to add new tools
- [ ] Predictable behavior

---

## Timeline Estimate

Phase | Estimated Effort | Dependencies
------|-----------------|-------------
1. Registry & Contracts | 2-3 days | None
2. Dispatch Refactor | 3-4 days | Phase 1
3. Datasearch Engine | 2-3 days | Phase 1
4. WP6 Enhancement | 3-4 days | Phase 1, 2
5. WP7 Enhancement | 2-3 days | Phase 1, 2
6. Documentation | 1-2 days | All phases

**Total**: 13-19 days (sequential implementation)

---

## Approval Gates

Before starting implementation:
- [x] Operator approves this plan
- [ ] Operator confirms git hygiene approach (stash/commit/reset)
- [ ] Operator approves any dashboard prompt changes

Before each phase:
- [ ] Previous phase tests pass
- [ ] No regressions in existing functionality
- [ ] Code review completed

---

## Next Steps

1. **Immediate**: Operator approval of this updated plan
2. **Phase 1 Start**: Create registry and contract modules
3. **Continuous**: Run tests after each change
4. **Before Phase 4**: Review and approve prompt changes
5. **Final**: Full integration testing and documentation review

---

**End of Updated Implementation Plan**
