# Best Practices Reference — OmniFlowBeta

**Purpose**: Catalog of proven patterns extracted from OmniFlowCentral and CV Generator research  
**Audience**: Developers, Operators, AI Agents  
**Last Updated**: 2026-02-05

---

## Table of Contents

1. [Architecture Patterns](#architecture-patterns)
2. [Tool Design Patterns](#tool-design-patterns)
3. [Prompting Patterns](#prompting-patterns)
4. [Error Handling](#error-handling)
5. [Data Access Patterns](#data-access-patterns)
6. [Testing Patterns](#testing-patterns)
7. [Documentation Standards](#documentation-standards)

---

## Architecture Patterns

### 1.1 Registry-Driven Design

**Pattern**: Single source of truth for tool definitions

**From**: OmniFlowCentral

**Implementation**:
```python
# Define all tools in one place
TOOL_SPECS = {
    "tool_name": {
        "description": "What this tool does",
        "params": {
            "param_name": {
                "type": "str|int|bool|list|dict",
                "required": True|False,
                "default": <value>,
                "description": "What this param does"
            }
        },
        "aliases": {
            "old_param_name": "new_param_name"
        },
        "examples": [
            {"input": {...}, "output": {...}}
        ]
    }
}

# Separate dispatch table
TOOL_HANDLERS = {
    "canonical_name": handler_function
}
```

**Benefits**:
- Single source of truth
- Easy to add new tools
- Consistent validation
- Auto-generated documentation possible

**Anti-pattern**: Tool definitions scattered across codebase

---

### 1.2 Modular Service Layers

**Pattern**: Separate concerns into focused modules

**Structure**:
```
backend/
├── shared/               # Cross-cutting utilities
│   ├── tool_specs.py     # Tool definitions
│   ├── tool_registry.py  # Registry functions
│   ├── error_codes.py    # Error handling
│   └── user_validator.py # User management
├── tool_call_handler/    # Orchestration layer
│   ├── __init__.py       # Entry point (thin)
│   ├── dispatch.py       # Dispatch pipeline
│   ├── handlers/         # Tool handlers
│   │   ├── blob_handlers.py
│   │   ├── data_handlers.py
│   │   └── search_handlers.py
│   ├── wp6/              # Context builder
│   │   ├── fast_context.py
│   │   ├── deep_context.py
│   │   └── routing.py
│   └── wp7/              # Semantic indexer
│       ├── batch.py
│       └── dedup.py
└── tools/                # Individual tool functions
```

**Benefits**:
- Clear boundaries
- Easy to test
- Reduced coupling
- Better code navigation

---

### 1.3 Parameter Normalization Pipeline

**Pattern**: Canonicalize inputs before processing

**From**: OmniFlowCentral

**Pipeline**:
```python
def normalize_tool_and_params(contract: dict) -> tuple[str, dict]:
    # 1. Extract raw inputs
    raw_tool = contract.get("tool") or ""
    params = contract.get("payload", {}).get("params", {})
    
    # 2. Canonicalize tool name
    canonical = canonical_tool_name(raw_tool)
    
    # 3. Apply parameter aliases
    params = apply_param_aliases(canonical, params)
    
    # 4. Filter to allowed fields
    params = filter_allowed_fields(canonical, params)
    
    # 5. Validate required fields
    validate_required_params(canonical, params)
    
    return canonical, params
```

**Benefits**:
- Handles legacy names
- Consistent validation
- Security (field filtering)
- Clear error messages

---

## Tool Design Patterns

### 2.1 Dataset Search Pattern

**Pattern**: Manifest-first, bounded retrieval

**From**: OmniFlowCentral query_dataset

**Contract**:
```python
# Input
{
    "q": "search text",           # Optional
    "filters": {                  # Optional filters
        "category": "...",
        "tags_any": [...],
        "tags_all": [...]
    },
    "limit": 20,                  # Max results
    "cursor": "...",              # Pagination
    "fetch_content": False        # Inline content
}

# Output
{
    "status": "success",
    "total_matched": 100,
    "total_returned": 20,
    "cursor": "next_page_token",
    "items": [
        {
            "blob_name": "...",
            "display_name": "...",
            "summary": "...",
            "tags": [...],
            "category": "...",
            "updated_at": "ISO8601",
            "score": 0.95,
            "_content": "..."          # Only if fetch_content=true
        }
    ]
}
```

**Key Principles**:
1. **Scan → Confirm → Fetch** workflow
   - First: Search without content (`fetch_content=false`)
   - Then: Confirm specific items
   - Finally: Fetch full content only when needed

2. **Deterministic IDs**
   - Use stable, reproducible identifiers
   - Example: `DU/1991/350` (publisher/year/position)

3. **Bounded Operations**
   - Hard limits on results (`limit`)
   - Cursor pagination for large datasets
   - No full scans by default

4. **Content Slicing**
   - Support partial content retrieval
   - `content_slice: {start: 0, length: 2048}`
   - Truncation flags: `_fullTextTruncated: true`

**Anti-patterns**:
- ❌ Loading full content by default
- ❌ Unbounded searches
- ❌ Fragile title/text matching

---

### 2.2 Batch Operations Pattern

**Pattern**: Prefer batch over single-item operations

**From**: OmniFlowBeta read_many_blobs, WP7

**Example**:
```python
# ❌ Anti-pattern: Multiple single reads
for file in files:
    result = read_blob_file(file)

# ✅ Pattern: Single batch read
results = read_many_blobs(files, max_bytes_per_file=10240)
```

**Batch Read Contract**:
```python
{
    "files": ["file1.json", "file2.json"],
    "tail_lines": 100,           # Last N lines only
    "tail_bytes": 65536,         # Byte limit for tail
    "max_bytes_per_file": 262144, # Per-file limit
    "parse_json": True,          # Auto-parse JSON
    "max_files": 50              # Hard limit on count
}
```

**Benefits**:
- Reduced latency (1 call vs N calls)
- Lower costs (fewer API calls)
- Better error handling (atomic operation)
- Resource efficiency

---

### 2.3 User Isolation Pattern

**Pattern**: Strict namespace separation

**From**: OmniFlowCentral

**Implementation**:
```python
def get_user_id_from_request(req) -> tuple[str, bool]:
    # 1. Check header
    user_id = req.headers.get("X-User-Id")
    if user_id and validate_user_id(user_id):
        return user_id, True
    
    # 2. Check query param
    user_id = req.params.get("user_id")
    if user_id and validate_user_id(user_id):
        return user_id, True
    
    # 3. Check body
    user_id = req.get_json().get("user_id")
    if user_id and validate_user_id(user_id):
        return user_id, True
    
    # 4. Fallback to default
    return os.getenv("OMNIFLOW_DEFAULT_USER_ID", "default"), False

def validate_user_id(user_id: str) -> bool:
    # Alphanumeric, dash, underscore only
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', user_id))

def get_user_blob_path(user_id: str, blob_name: str) -> str:
    # Always prefix with user namespace
    return f"users/{user_id}/{blob_name.lstrip('/')}"
```

**Security Principles**:
- ✓ Validate user_id format
- ✓ Namespace all blob paths
- ✓ Never allow path traversal (`../`)
- ✓ Log user_id in all operations

---

## Prompting Patterns

### 3.1 Persona Pattern

**Pattern**: Define explicit role for the AI

**From**: CV Generator research

**Example**:
```python
system_prompt = """You are an expert Context Builder for OmniFlow.

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
"""
```

**Benefits**:
- Clearer expectations
- More consistent outputs
- Better error handling
- Easier to debug

---

### 3.2 Structured Output Pattern

**Pattern**: Enforce strict JSON schemas

**From**: CV Generator research + OpenAI best practices

**Implementation**:
```python
from pydantic import BaseModel
from typing import Literal, Optional, List, Dict

class ContextPackV1(BaseModel):
    schema_version: Literal["omniflow.context_pack.v1"] = "omniflow.context_pack.v1"
    run_id: str
    mode: Literal["FAST", "DEEP"]
    budgets: Dict[str, int]
    layers: Dict[str, Any]
    created_utc: str
    pack_tokens_est: int

# In prompt
prompt = f"""Generate a context pack following this exact schema:
{ContextPackV1.schema_json(indent=2)}

Output ONLY valid JSON matching this schema.
"""

# Validate response
try:
    pack = ContextPackV1.parse_raw(response.content)
except ValidationError as e:
    return ToolError("SCHEMA_VIOLATION", f"Invalid context pack: {e}")
```

**Benefits**:
- Type safety
- Auto-validation
- Clear errors
- Documentation from code

---

### 3.3 Few-Shot Pattern

**Pattern**: Provide examples in prompts

**Example**:
```python
prompt = """Categorize the interaction.

Example 1:
Input: "Analyze my tax documents"
Output: {"category": "tax", "confidence": 0.95}

Example 2:
Input: "What's the weather?"
Output: {"category": "general", "confidence": 0.6}

Now categorize:
Input: "{user_message}"
Output:"""
```

**Benefits**:
- Faster learning
- More consistent output
- Reduced errors
- Clear expectations

---

### 3.4 Section Delimiter Pattern

**Pattern**: Clear markers for different parts

**Example**:
```python
def build_agent_input(context, user_message):
    parts = []
    
    if context:
        parts.append("[FAST_CONTEXT]")
        parts.append(context)
        parts.append("")  # Blank line
    
    parts.append("[USER_MESSAGE]")
    parts.append(user_message)
    
    return "\n".join(parts)
```

**Benefits**:
- Clear structure
- Easy to parse
- Reduces confusion
- Better debugging

---

### 3.5 Negative Constraints Pattern

**Pattern**: Explicitly state what NOT to do

**Example**:
```python
system_prompt = """...

CRITICAL CONSTRAINTS:
- DO NOT include personal identifiable information (PII)
- DO NOT perform full blob scans or directory listings
- DO NOT exceed the token budget under any circumstances
- DO NOT cache sensitive data
- DO NOT retry on explicit user cancellation

PREFERENCES ENFORCEMENT:
- IF user preferences disable_history_reads=true, BLOCK access to interactions/*
- IF allowed_reads list exists, ALLOW ONLY listed files + system files
- IF semantic_only=true, USE ONLY semantic index (no raw reads)
"""
```

**Benefits**:
- Prevents common errors
- Security enforcement
- Clear boundaries
- Audit compliance

---

## Error Handling

### 4.1 Error Code Taxonomy

**Pattern**: Structured, actionable error codes

**From**: OmniFlowCentral

**Error Codes**:
```python
ERROR_CODES = {
    # Client errors (4xx)
    "MISSING_PARAM": {
        "status": 400,
        "description": "Required parameter not provided",
        "user_action": "Provide the required parameter"
    },
    "VALIDATION_FAILED": {
        "status": 400,
        "description": "Parameter validation failed",
        "user_action": "Check parameter format and try again"
    },
    "INVALID_TOOL": {
        "status": 404,
        "description": "Tool not found in registry",
        "user_action": "Use a valid tool name from capabilities"
    },
    "AUTHORIZATION_FAILED": {
        "status": 403,
        "description": "User not authorized for this operation",
        "user_action": "Check permissions and user_id"
    },
    "PREFERENCES_BLOCKED": {
        "status": 403,
        "description": "Operation blocked by user preferences",
        "user_action": "Modify preferences or request access"
    },
    "RATE_LIMITED": {
        "status": 429,
        "description": "Too many requests",
        "user_action": "Wait and retry"
    },
    
    # Server errors (5xx)
    "UPSTREAM_ERROR": {
        "status": 500,
        "description": "External service failure",
        "user_action": "Retry later or contact support"
    },
    "TIMEOUT": {
        "status": 504,
        "description": "Operation timed out",
        "user_action": "Retry with smaller request"
    },
    "SCHEMA_VIOLATION": {
        "status": 500,
        "description": "Output schema validation failed",
        "user_action": "Report to developers (internal error)"
    }
}
```

**ToolError Class**:
```python
class ToolError(Exception):
    def __init__(self, code: str, message: str, details: dict = None, status: int = None):
        self.code = code
        self.message = message
        self.details = details or {}
        self.status = status or ERROR_CODES.get(code, {}).get("status", 500)
        super().__init__(f"{code}: {message}")

def build_error_payload(code: str, message: str, details: dict = None) -> dict:
    return {
        "status": "error",
        "code": code,
        "message": message,
        "details": details or {},
        "user_action": ERROR_CODES.get(code, {}).get("user_action"),
        "timestamp": datetime.utcnow().isoformat()
    }
```

**Benefits**:
- Actionable error messages
- Consistent structure
- Easy to monitor
- Clear debugging

**Anti-pattern**: Generic "Error" or "Internal server error"

---

### 4.2 Trace ID Pattern

**Pattern**: Request tracking across services

**From**: OmniFlowCentral

**Implementation**:
```python
def handle_request(req):
    # Generate or extract trace_id
    trace_id = req.headers.get("X-Trace-Id") or str(uuid.uuid4())
    
    try:
        # Include in all logs
        logger.info("Processing request", extra={"trace_id": trace_id})
        
        result = process_request(req)
        
        # Include in response
        return {
            "status": "success",
            "trace_id": trace_id,
            "result": result
        }
    except Exception as e:
        logger.error("Request failed", exc_info=True, extra={"trace_id": trace_id})
        return {
            "status": "error",
            "trace_id": trace_id,
            "message": str(e)
        }
```

**Benefits**:
- Easy debugging
- Cross-service tracing
- Error correlation
- Audit trails

---

## Data Access Patterns

### 5.1 Preference-Based Access Control

**Pattern**: User-controlled data access restrictions

**From**: OmniFlowBeta WP6

**Schema**:
```json
{
  "schema_version": "omniflow.preferences.v1",
  "disable_history_reads": false,
  "allowed_reads": [
    "TM.json",
    "LO.json",
    "PS.json",
    "projects/*"
  ],
  "semantic_only": false,
  "updated_utc": "2026-02-05T12:00:00Z"
}
```

**Implementation**:
```python
def check_read_permission(user_id: str, blob_path: str) -> bool:
    prefs = load_preferences(user_id)
    
    # System files always allowed
    if is_system_file(blob_path):
        return True
    
    # Semantic paths always allowed
    if blob_path.startswith("interactions/semantic/") or \
       blob_path.startswith("interactions/portfolio/"):
        return True
    
    # Check disable_history_reads
    if prefs.get("disable_history_reads"):
        if blob_path.startswith("interactions/"):
            return False
    
    # Check allowed_reads list
    allowed = prefs.get("allowed_reads")
    if allowed:
        return any(matches_pattern(blob_path, pattern) for pattern in allowed)
    
    # Default: allow
    return True
```

**Benefits**:
- User privacy control
- Prevent agent browsing
- Compliance support
- Flexible policies

---

### 5.2 Bounded Read Pattern

**Pattern**: Never unbounded scans

**Principles**:
1. **Always limit results**
   ```python
   def list_blobs(prefix, limit=100):
       # Hard cap
       limit = min(limit, MAX_RESULTS)
   ```

2. **Support pagination**
   ```python
   def search(q, cursor=None, limit=20):
       # Use cursor for stable pagination
       results = query(q, after=cursor, limit=limit)
       return {
           "items": results,
           "cursor": results[-1].id if results else None
       }
   ```

3. **Tail reads for logs**
   ```python
   def read_log(path, tail_lines=100):
       # Read from end, not beginning
       return read_tail(path, lines=tail_lines, max_bytes=65536)
   ```

4. **Bounded content fetch**
   ```python
   def get_content(path, max_bytes=262144):
       # Truncate large files
       content = read_prefix(path, max_bytes=max_bytes)
       return {
           "content": content,
           "truncated": len_on_disk > max_bytes
       }
   ```

**Benefits**:
- Predictable performance
- Cost control
- Prevents timeouts
- Better UX

---

## Testing Patterns

### 6.1 Contract Tests

**Pattern**: Test interfaces, not implementation

**Example**:
```python
def test_tool_contract():
    """Test that tool follows standard contract"""
    # Given
    params = {"target_blob_name": "test.json"}
    
    # When
    result = handle_read_blob(params, user_id="test_user")
    
    # Then - verify contract
    assert "status" in result
    assert result["status"] in ("success", "error")
    
    if result["status"] == "success":
        assert "data" in result
        assert "user_id" in result
    else:
        assert "code" in result
        assert "message" in result

def test_error_contract():
    """Test that errors follow standard contract"""
    # Given - missing required param
    params = {}
    
    # When
    result = handle_read_blob(params, user_id="test_user")
    
    # Then
    assert result["status"] == "error"
    assert result["code"] == "MISSING_PARAM"
    assert "message" in result
    assert "target_blob_name" in result["message"]
```

**Benefits**:
- Tests behavior, not internals
- Survives refactoring
- Clear expectations
- Easy to maintain

---

### 6.2 Golden Tests

**Pattern**: Reference outputs for regression detection

**Example**:
```python
def test_context_pack_schema():
    """Test that context pack matches golden schema"""
    # Given
    user_message = "Analyze my tax documents"
    
    # When
    pack = build_context_pack(user_message)
    
    # Then
    assert pack["schema_version"] == "omniflow.context_pack.v1"
    assert "run_id" in pack
    assert "mode" in pack
    assert pack["mode"] in ("FAST", "DEEP")
    assert "budgets" in pack
    assert isinstance(pack["budgets"], dict)
```

---

## Documentation Standards

### 7.1 Tool Documentation Template

**Pattern**: Consistent tool docs

**Template**:
```markdown
# Tool: tool_name

## Purpose
One-line description of what this tool does.

## Contract

### Input
\`\`\`json
{
  "param1": "type (required|optional)",
  "param2": "type (required|optional, default: value)"
}
\`\`\`

### Output
\`\`\`json
{
  "status": "success|error",
  "result": {...}
}
\`\`\`

## Examples

### Example 1: Basic usage
\`\`\`json
{
  "tool": "tool_name",
  "param1": "value1"
}
\`\`\`

**Response:**
\`\`\`json
{
  "status": "success",
  "result": {...}
}
\`\`\`

### Example 2: Error case
\`\`\`json
{
  "tool": "tool_name"
}
\`\`\`

**Response:**
\`\`\`json
{
  "status": "error",
  "code": "MISSING_PARAM",
  "message": "..."
}
\`\`\`

## Common Pitfalls

- ❌ Don't do X (explain why)
- ✅ Do Y instead

## Notes

- Additional context
- Performance considerations
- Security notes
```

---

### 7.2 Prompt Documentation Template

**Pattern**: Document prompt contracts

**Template**:
```markdown
# Prompt: prompt_name

## Dashboard ID
\`OPENAI_PROMPT_ID_NAME\`

## Purpose
What this prompt does.

## Required Settings

### Model
- Model: gpt-4o
- Temperature: 0.7
- Max tokens: 4096

### Tools
- [ ] Tool 1
- [ ] Tool 2

### Instructions (in dashboard)
\`\`\`
[Copy exact instructions here]
\`\`\`

## Variables

Variable | Type | Required | Description
---------|------|----------|------------
user_message | string | Yes | User input
context | string | No | Additional context

## Output Schema

\`\`\`json
{
  "schema_version": "...",
  "field1": "...",
  "field2": "..."
}
\`\`\`

## Testing Checklist

- [ ] Model selected correctly
- [ ] Tools attached
- [ ] Instructions match template
- [ ] Variables configured
- [ ] Output schema validated
```

---

## Summary

**Key Takeaways:**

1. **Registry-Driven** - Single source of truth for all tools
2. **Bounded Operations** - Never unbounded scans or reads
3. **Strict Schemas** - Type-safe contracts everywhere
4. **Clear Errors** - Structured error codes and messages
5. **User Isolation** - Strict namespace separation
6. **Batch-First** - Prefer batch operations
7. **Prompt Patterns** - Persona, structured output, few-shot
8. **Test Contracts** - Test behavior, not implementation
9. **Document Everything** - Clear, consistent documentation

**Anti-Patterns to Avoid:**

- ❌ Scattered tool definitions
- ❌ Silent failures
- ❌ Unbounded operations
- ❌ Generic error messages
- ❌ Path traversal vulnerabilities
- ❌ Single-item operations when batch available
- ❌ Unstructured prompt outputs
- ❌ Missing documentation

---

**References:**
- OmniFlowCentral: https://github.com/dokuczacz/OmniFlowCentral
- OpenAI Prompt Engineering: https://platform.openai.com/docs/guides/prompting
- Pydantic: https://docs.pydantic.dev/
