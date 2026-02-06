# Architecture Analysis — OmniFlowBeta Enhancement

**Purpose**: Comparative analysis of OmniFlowBeta, OmniFlowCentral, and CV Generator patterns  
**Date**: 2026-02-05  
**Status**: Analysis Complete, Implementation Pending

---

## Executive Summary

This document compares the architecture and patterns across three systems to identify best practices for enhancing OmniFlowBeta's Tool Handler 1.

### Repositories Analyzed

1. **OmniFlowBeta** (Current System)
   - Azure Functions backend with multi-user isolation
   - Sophisticated tool orchestration (WP6/WP7)
   - ~3500 line tool_call_handler
   - Mature but needs refactoring

2. **OmniFlowCentral** (Reference System)
   - Clean, registry-driven architecture
   - TOOL_SPECS + TOOL_HANDLERS pattern
   - Dataset search implementation (query_dataset)
   - Best-in-class error handling

3. **CV Generator Patterns** (Research)
   - Industry best practices for prompting
   - Structured output patterns
   - Documentation standards
   - Example-driven approach

---

## Comparative Analysis

### 1. Tool Registration & Dispatch

#### OmniFlowBeta (Current)
```python
# Scattered across file
def execute_tool_call(tool_name, args, user_id):
    # Ad-hoc normalization
    if tool_name in ["read_blob", "read_blob_file"]:
        canonical = "read_blob_file"
    
    # Ad-hoc validation
    if tool_name == "manage_files":
        operation = args.get("operation")
        if operation not in ["rename", "delete"]:
            return {"error": "Invalid operation"}
    
    # Dispatch logic
    if in_process_available:
        try:
            from tools import dispatch_tool
            return dispatch_tool(canonical, args, user_id)
        except:
            pass
    
    # Fallback to HTTP
    return proxy_call(canonical, args)
```

**Issues:**
- No central registry
- Validation scattered
- Hard to add new tools
- Difficult to test

#### OmniFlowCentral (Reference)
```python
# Single source of truth
TOOL_SPECS = {
    "read_blob": {
        "params": {
            "name": {"type": "str", "required": True}
        },
        "aliases": {
            "target_blob_name": "name",
            "file_name": "name"
        }
    }
}

TOOL_HANDLERS = {
    "read_blob": _handle_read_blob
}

# Clean dispatch
def dispatch(contract):
    tool, params = _normalize_tool_and_params(contract)
    validate_tool_params(tool, params)
    handler = TOOL_HANDLERS[tool]
    return handler(params, user_id)
```

**Advantages:**
- Single source of truth
- Easy to add tools
- Centralized validation
- Testable components

**Recommendation:** Adopt TOOL_SPECS + TOOL_HANDLERS pattern

---

### 2. Error Handling

#### OmniFlowBeta (Current)
```python
# Inconsistent error returns
return {"error": "File not found"}
return {"status": "error", "message": "Invalid params"}
return {"error": str(e), "proxy_body": "..."}
```

**Issues:**
- Inconsistent structure
- No error codes
- Hard to debug
- No client guidance

#### OmniFlowCentral (Reference)
```python
# Structured errors
class ToolError(Exception):
    def __init__(self, code, message, details=None, status=None):
        self.code = code
        self.message = message
        self.details = details
        self.status = status

def build_error_payload(error: ToolError):
    return {
        "status": "error",
        "code": error.code,
        "message": error.message,
        "details": error.details,
        "trace_id": trace_id
    }

# Usage
raise ToolError("MISSING_PARAM", "Parameter 'name' is required")
```

**Advantages:**
- Consistent structure
- Actionable error codes
- Easy debugging with trace_id
- Client-friendly

**Recommendation:** Implement ToolError class and error taxonomy

---

### 3. Dataset Search

#### OmniFlowBeta (Current)
```python
# No unified search
# Various ad-hoc implementations:
# - get_filtered_data (single file)
# - WP7 semantic index search (embedded in WP6)
# - No manifest search

def _wp6_fast_context_from_wp7_semantic():
    # Hardcoded semantic search
    index = read_many_blobs(["interactions/semantic/index.jsonl"])
    # Parse, filter, rank...
```

**Issues:**
- No unified interface
- Embedded in WP6
- No pagination
- Limited to semantic data

#### OmniFlowCentral (Reference)
```python
# Unified dataset tool
def query_dataset(params):
    dataset = params.get("dataset")  # e.g., "eli_acts"
    q = params.get("q")
    limit = params.get("limit", 10)
    cursor = params.get("cursor")
    fetch_content = params.get("fetch_content", False)
    
    # Scan → Confirm → Fetch workflow
    results = search_manifest(dataset, q, cursor, limit)
    
    if fetch_content:
        results = attach_content(results, content_slice)
    
    return {
        "total_matched": len(results),
        "total_returned": min(len(results), limit),
        "items": results,
        "cursor": next_cursor
    }
```

**Advantages:**
- Unified interface
- Pagination support
- Bounded operations
- Clear workflow

**Recommendation:** Implement dataset_search tool following Central's pattern

---

### 4. Prompting Style

#### OmniFlowBeta (Current)
```python
# Direct string construction
input_msg = f"[FAST_CONTEXT]\n{ctx}\n\n[USER_MESSAGE]\n{msg}"

# Minimal prompt structure
system = "You are an AI assistant..."
```

**Issues:**
- Unstructured prompts
- No schema enforcement
- Hard to version
- Limited examples

#### CV Generator Patterns (Best Practices)
```python
# Persona pattern
system = """You are an expert Context Builder for OmniFlow.

Your role:
- Analyze user interaction history
- Select the most relevant context items
- Build compact, focused context packs
- Respect token budgets strictly

Your constraints:
- NEVER exceed the token budget
- ALWAYS include schema_version in output
- DO NOT include sensitive information
- PREFER recent, high-relevance items

Output format:
{json_schema}

Example:
Input: "Analyze my tax documents"
Output: {example_output}
"""

# Structured output validation
response_schema = ContextPackV1.schema_json()
```

**Advantages:**
- Clear role definition
- Explicit constraints
- Schema enforcement
- Example-driven

**Recommendation:** Apply persona, structured output, and few-shot patterns

---

### 5. User Isolation

#### OmniFlowBeta (Current)
```python
# Good isolation but inconsistent extraction
user_id = req.headers.get("X-User-Id") or "default"

# Manual namespace construction
blob_path = f"users/{user_id}/{file_name}"
```

**Strengths:**
- Multi-user support
- Namespace isolation
- Preference-based access control

#### OmniFlowCentral (Reference)
```python
# Strict validation
def get_user_id_from_request(req):
    user_id = (
        req.headers.get("X-User-Id") or
        req.params.get("user_id") or
        req.get_json().get("user_id") or
        os.getenv("OMNIFLOW_DEFAULT_USER_ID", "default")
    )
    
    if not validate_user_id(user_id):
        raise ToolError("VALIDATION_FAILED", "Invalid user_id format")
    
    return user_id

def validate_user_id(user_id: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', user_id))
```

**Advantages:**
- Multiple extraction sources
- Format validation
- Clear fallback chain
- Security enforcement

**Recommendation:** Add strict user_id validation

---

### 6. Batching & Performance

#### OmniFlowBeta (Current)
```python
# Excellent batch support
def read_many_blobs(files, tail_lines, max_bytes_per_file):
    # Efficient multi-read
    results = []
    for file in files[:max_files]:
        content = read_with_limits(file, max_bytes_per_file, tail_lines)
        results.append(parse_if_json(content))
    return results

# WP7 batch-first indexing
def wp7_batch_process(queue):
    batch = collect_items(queue, target_tokens=2000)
    semantic_items = index_batch(batch)
    write_to_index(semantic_items)
```

**Strengths:**
- read_many_blobs is excellent
- WP7 batch processing
- Token-aware batching

**Minor improvements:**
- Ensure all WP7 paths use batching
- Add prompt caching for cost reduction

**Recommendation:** Maintain batch-first approach, add prompt caching

---

## Key Architectural Patterns to Apply

### Pattern 1: Registry-Driven Tools

**What**: Single source of truth for all tool definitions

**Why**:
- Easy to add new tools
- Consistent validation
- Auto-generated documentation
- Single place to update

**How**:
```python
# backend/shared/tool_specs.py
TOOL_SPECS = {
    "tool_name": {
        "description": "...",
        "params": {...},
        "aliases": {...},
        "examples": [...]
    }
}

# backend/shared/tool_registry.py
def canonical_tool_name(raw): ...
def apply_param_aliases(tool, params): ...
def validate_tool_params(tool, params): ...
```

---

### Pattern 2: Structured Error Taxonomy

**What**: Consistent error codes and payloads

**Why**:
- Easy debugging
- Client-friendly
- Monitorable
- Actionable

**How**:
```python
# backend/shared/error_codes.py
class ToolError(Exception):
    def __init__(self, code, message, details=None):
        self.code = code
        self.message = message
        self.details = details

ERROR_CODES = {
    "MISSING_PARAM": 400,
    "VALIDATION_FAILED": 400,
    "INVALID_TOOL": 404,
    "PREFERENCES_BLOCKED": 403,
    "UPSTREAM_ERROR": 500
}
```

---

### Pattern 3: Bounded Datasearch

**What**: Manifest-first search with strict limits

**Why**:
- Predictable performance
- Cost control
- Better UX
- No timeouts

**How**:
```python
def dataset_search(q, filters, limit, cursor):
    # 1. Load manifest (fast)
    manifest = load_manifest(user_id)
    
    # 2. Filter in-memory (cheap)
    results = filter_entries(manifest, q, filters)
    
    # 3. Sort deterministically
    results = sort_by(results, "updated_at desc", "blob_name asc")
    
    # 4. Paginate
    page = paginate(results, cursor, limit)
    
    # 5. Return with next cursor
    return {
        "items": page,
        "cursor": generate_cursor(page[-1]) if page else None
    }
```

---

### Pattern 4: Persona-Driven Prompts

**What**: Explicit role definition in system prompts

**Why**:
- Clearer expectations
- Better outputs
- Easier debugging
- More consistent

**How**:
```python
system_prompt = """You are an expert {role} for OmniFlow.

Your role:
- {responsibility_1}
- {responsibility_2}

Your constraints:
- NEVER {constraint_1}
- ALWAYS {constraint_2}
- DO NOT {constraint_3}

Output format:
{json_schema}

Example:
Input: {example_input}
Output: {example_output}
"""
```

---

### Pattern 5: Modular Architecture

**What**: Small, focused modules instead of "god files"

**Why**:
- Easier to understand
- Easier to test
- Easier to maintain
- Better separation of concerns

**Structure**:
```
backend/tool_call_handler/
├── __init__.py           # Thin entry point (~200 lines)
├── dispatch.py           # Dispatch pipeline (~300 lines)
├── handlers/             # Tool handlers
│   ├── blob_handlers.py
│   ├── data_handlers.py
│   └── search_handlers.py
├── wp6/                  # Context builder
│   ├── fast_context.py
│   ├── deep_context.py
│   ├── routing.py
│   └── cache.py
└── wp7/                  # Semantic indexer
    ├── batch.py
    └── dedup.py
```

---

## Implementation Priority

### High Priority (Phase 1-2)
1. **Registry & Contracts** - Foundation for everything else
2. **Error Taxonomy** - Improves debugging immediately
3. **Dispatch Refactor** - Enables modularization

### Medium Priority (Phase 3-4)
4. **Datasearch Engine** - New capability, high value
5. **WP6 Modularization** - Improves maintainability

### Lower Priority (Phase 5-6)
6. **WP7 Enhancement** - Already good, minor improvements
7. **Documentation** - Important but can lag implementation

---

## Metrics for Success

### Code Quality
- Tool handler <1500 lines (currently ~3500)
- Test coverage >80% (currently unknown)
- Zero ad-hoc validations
- All tools in registry

### Performance
- Search <1s for 1000+ items
- Prompt cache hit rate >80%
- API call reduction >50%

### Developer Experience
- New tool addition <30 minutes
- Clear error messages (no "Internal server error")
- Comprehensive documentation
- Easy local testing

---

## Risk Assessment

### Low Risk
- ✅ Registry pattern (proven in Central)
- ✅ Error taxonomy (standard practice)
- ✅ Batch operations (already working)

### Medium Risk
- ⚠️ Dispatch refactor (large code change)
- ⚠️ WP6 modularization (complex logic)
- ⚠️ Prompt changes (requires testing)

### High Risk
- 🔴 Breaking changes (must maintain compatibility)
- 🔴 Dashboard prompt drift (outside code control)
- 🔴 Performance regression (careful benchmarking needed)

---

## Conclusion

The analysis reveals clear opportunities to enhance OmniFlowBeta by applying proven patterns from OmniFlowCentral and industry best practices:

**Strengths to Preserve:**
- Sophisticated WP6/WP7 architecture
- Excellent batch operations
- Strong user isolation
- Preference-based access control

**Areas for Improvement:**
- Modularize tool_call_handler (reduce from 3500+ to <1500 lines)
- Implement registry-driven tool system
- Add structured error taxonomy
- Create unified datasearch capability
- Apply prompting best practices

**Expected Outcomes:**
- More maintainable codebase
- Easier to add new features
- Better error handling
- Improved performance through caching
- Clearer documentation

The phased implementation plan ensures incremental progress with minimal risk.

---

**Next Step**: Operator approval to begin Phase 1 (Registry & Contracts)
