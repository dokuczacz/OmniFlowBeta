# Quick Start Guide - Tool Handler 1 Refactor

**For**: Operators and Developers starting implementation  
**Status**: Ready to begin Phase 1  
**Last Updated**: 2026-02-05

---

## 🎯 What This Refactor Does

Transforms OmniFlowBeta's Tool Handler from a monolithic 3500+ line file into a modular, registry-driven architecture with best practices from OmniFlowCentral and industry research.

**Key Benefits:**
- ✅ Easier to maintain and extend
- ✅ Better error handling and debugging
- ✅ Improved performance through caching
- ✅ Unified datasearch capability
- ✅ Clear documentation and contracts

---

## 📚 Read This First

### For Quick Overview (5 minutes)
👉 **PLANNING_SUMMARY.md** - High-level summary, status, next steps

### For Full Understanding (30 minutes)
👉 **IMPLEMENTATION_PLAN_UPDATED.md** - Complete 6-phase plan with details

### For Implementation Reference (ongoing)
👉 **docs/BEST_PRACTICES_REFERENCE.md** - Pattern catalog to follow while coding

### For Context and Rationale (20 minutes)
👉 **docs/ARCHITECTURE_ANALYSIS.md** - Why we're making these changes

---

## 🚦 Current Status

**Planning**: ✅ Complete  
**Implementation**: ⏳ Awaiting approval to start Phase 1  
**Testing**: ⏳ Not started  
**Documentation**: ⏳ Not started  

---

## 🏃 Quick Start - Phase 1

Once approved, here's exactly what to do:

### Step 1: Create Tool Registry (Day 1)

```bash
# Create the file
touch backend/shared/tool_specs.py
```

```python
# backend/shared/tool_specs.py
"""
Tool specifications registry - Single source of truth for all tools.
"""

TOOL_SPECS = {
    "read_blob_file": {
        "description": "Read a single blob file by name",
        "params": {
            "file_name": {
                "type": "str",
                "required": True,
                "description": "Full path inside user namespace"
            }
        },
        "aliases": {
            "target_blob_name": "file_name",
            "blob_name": "file_name",
            "name": "file_name"
        },
        "examples": [
            {
                "input": {"file_name": "TM.json"},
                "output": {"status": "success", "data": {...}}
            }
        ]
    },
    # Add more tools...
}
```

### Step 2: Create Error Handling (Day 1)

```bash
touch backend/shared/error_codes.py
```

```python
# backend/shared/error_codes.py
"""
Structured error codes and handling.
"""

class ToolError(Exception):
    """Structured tool error with code and details."""
    
    def __init__(self, code: str, message: str, details: dict = None, status: int = None):
        self.code = code
        self.message = message
        self.details = details or {}
        self.status = status or ERROR_CODES.get(code, {}).get("status", 500)
        super().__init__(f"{code}: {message}")

ERROR_CODES = {
    "MISSING_PARAM": {"status": 400, "description": "Required parameter not provided"},
    "VALIDATION_FAILED": {"status": 400, "description": "Parameter validation failed"},
    "INVALID_TOOL": {"status": 404, "description": "Tool not found"},
    "PREFERENCES_BLOCKED": {"status": 403, "description": "Blocked by user preferences"},
    "UPSTREAM_ERROR": {"status": 500, "description": "External service failure"},
}

def build_error_payload(code: str, message: str, details: dict = None) -> dict:
    return {
        "status": "error",
        "code": code,
        "message": message,
        "details": details or {},
        "timestamp": datetime.utcnow().isoformat()
    }
```

### Step 3: Create Registry Functions (Day 2)

```bash
touch backend/shared/tool_registry.py
```

```python
# backend/shared/tool_registry.py
"""
Tool registry functions - Canonical names, aliases, validation.
"""
from .tool_specs import TOOL_SPECS
from .error_codes import ToolError

def canonical_tool_name(raw_name: str) -> str:
    """Convert any tool name to canonical form."""
    raw = raw_name.strip().lower()
    
    # Already canonical
    if raw in TOOL_SPECS:
        return raw
    
    # Check aliases across all tools
    for canonical, spec in TOOL_SPECS.items():
        if raw in spec.get("aliases", {}).values():
            return canonical
    
    return raw  # Return as-is if unknown

def apply_param_aliases(tool: str, params: dict) -> dict:
    """Apply parameter aliases for a tool."""
    spec = TOOL_SPECS.get(tool)
    if not spec:
        return params
    
    aliases = spec.get("aliases", {})
    normalized = {}
    
    for key, value in params.items():
        # Use canonical name if alias found
        canonical_key = aliases.get(key, key)
        normalized[canonical_key] = value
    
    return normalized

def validate_tool_params(tool: str, params: dict) -> None:
    """Validate that required params are present."""
    spec = TOOL_SPECS.get(tool)
    if not spec:
        raise ToolError("INVALID_TOOL", f"Unknown tool: {tool}")
    
    param_specs = spec.get("params", {})
    
    for param_name, param_spec in param_specs.items():
        if param_spec.get("required") and param_name not in params:
            raise ToolError(
                "MISSING_PARAM",
                f"Missing required parameter: {param_name}",
                {"tool": tool, "param": param_name}
            )
```

### Step 4: Write Tests (Day 2-3)

```bash
touch tests/unit/test_tool_registry.py
```

```python
# tests/unit/test_tool_registry.py
import pytest
from backend.shared.tool_registry import canonical_tool_name, apply_param_aliases
from backend.shared.error_codes import ToolError

def test_canonical_tool_name_direct():
    assert canonical_tool_name("read_blob_file") == "read_blob_file"

def test_canonical_tool_name_alias():
    assert canonical_tool_name("read_blob") == "read_blob_file"

def test_apply_param_aliases():
    params = {"target_blob_name": "test.json"}
    result = apply_param_aliases("read_blob_file", params)
    assert result == {"file_name": "test.json"}

def test_validate_missing_param():
    with pytest.raises(ToolError) as exc:
        validate_tool_params("read_blob_file", {})
    assert exc.value.code == "MISSING_PARAM"
```

### Step 5: Update Catalog (Day 3)

Update `AGENT_FUNCTIONS_CATALOG.json` to match your TOOL_SPECS.

```json
{
  "schema_version": "omniflow.agent_functions.v1",
  "tools": [
    {
      "operation_id": "read_blob_file",
      "purpose": "Read a single blob file by name",
      "inputs": {
        "file_name": "string (required)"
      },
      "examples": [
        {
          "request": "GET /api/read_blob_file?file_name=TM.json"
        }
      ],
      "gotchas": [
        "If basename only and ambiguous, returns candidates[]"
      ]
    }
  ]
}
```

### Step 6: Run Tests

```bash
cd /home/runner/work/OmniFlowBeta/OmniFlowBeta
pytest tests/unit/test_tool_registry.py -v
```

---

## 🔍 How to Check Progress

After each step, verify:

```bash
# Check file exists
ls -la backend/shared/tool_specs.py

# Check it loads
python -c "from backend.shared.tool_specs import TOOL_SPECS; print(len(TOOL_SPECS))"

# Run tests
pytest tests/unit/ -v

# Check git status
git status
```

---

## 📋 Phase 1 Checklist

Use this to track Phase 1 progress:

- [ ] Created `backend/shared/tool_specs.py`
  - [ ] Defined TOOL_SPECS dictionary
  - [ ] Added at least 5 tools
  - [ ] Included params, aliases, examples for each
  
- [ ] Created `backend/shared/error_codes.py`
  - [ ] ToolError exception class
  - [ ] ERROR_CODES dictionary
  - [ ] build_error_payload() function
  
- [ ] Created `backend/shared/tool_registry.py`
  - [ ] canonical_tool_name() function
  - [ ] apply_param_aliases() function
  - [ ] validate_tool_params() function
  
- [ ] Updated `AGENT_FUNCTIONS_CATALOG.json`
  - [ ] Matches TOOL_SPECS
  - [ ] Includes examples
  - [ ] Documents gotchas
  
- [ ] Created tests
  - [ ] tests/unit/test_tool_registry.py
  - [ ] At least 5 test cases
  - [ ] All tests passing
  
- [ ] Documentation
  - [ ] Inline docstrings
  - [ ] Type hints
  - [ ] Examples in comments

---

## ⚠️ Common Pitfalls to Avoid

### ❌ Don't:
- Add tools outside TOOL_SPECS (breaks single source of truth)
- Use generic errors like "Error" (use ToolError with codes)
- Skip tests (they catch regressions)
- Change existing tool behavior (maintain backward compatibility)
- Commit without running tests

### ✅ Do:
- Follow the pattern catalog (BEST_PRACTICES_REFERENCE.md)
- Write tests first (TDD)
- Keep changes small and incremental
- Document as you go
- Ask for review before merging

---

## 🆘 Getting Help

### If You're Stuck:
1. Read **BEST_PRACTICES_REFERENCE.md** for the pattern
2. Look at **ARCHITECTURE_ANALYSIS.md** for examples
3. Check **IMPLEMENTATION_PLAN_UPDATED.md** for details
4. Review OmniFlowCentral code for reference

### If Tests Fail:
1. Read the error message carefully
2. Check your TOOL_SPECS syntax
3. Verify imports are correct
4. Run single test: `pytest tests/unit/test_tool_registry.py::test_name -v`

### If Confused About Design:
1. Re-read the relevant section in IMPLEMENTATION_PLAN_UPDATED.md
2. Look at OmniFlowCentral's implementation
3. Check ARCHITECTURE_ANALYSIS.md for rationale

---

## 📊 Measuring Success

After Phase 1, you should have:

**Metrics:**
- ✅ All existing tools in TOOL_SPECS
- ✅ All tests passing
- ✅ Error codes defined and used
- ✅ Registry functions working
- ✅ Documentation updated

**Outcome:**
- Foundation for all subsequent phases
- Clear contract for all tools
- Standardized error handling
- Easy to add new tools

---

## 🚀 After Phase 1

Once Phase 1 is complete and approved:

1. **Report Progress**: Commit and push changes
2. **Review**: Code review with operator
3. **Move to Phase 2**: Dispatch pipeline refactor
4. **Continue**: Follow IMPLEMENTATION_PLAN_UPDATED.md

---

## 📖 Additional Resources

- **OmniFlowCentral**: https://github.com/dokuczacz/OmniFlowCentral
- **OpenAI Prompting**: https://platform.openai.com/docs/guides/prompting
- **Pydantic Docs**: https://docs.pydantic.dev/
- **Pytest Docs**: https://docs.pytest.org/

---

## 💡 Pro Tips

1. **Keep it simple**: Don't over-engineer Phase 1
2. **Test early**: Write tests as you code
3. **Stay focused**: Resist adding features beyond the phase scope
4. **Document**: Future you will thank present you
5. **Ask questions**: Better to ask than to guess

---

**Ready to Start?** → Begin with Step 1: Create Tool Registry

**Need Approval?** → Review IMPLEMENTATION_PLAN_UPDATED.md with operator

**Need Context?** → Read PLANNING_SUMMARY.md and ARCHITECTURE_ANALYSIS.md

---

Good luck! 🎯 You've got this! The planning is solid, the patterns are proven, and the path is clear.
