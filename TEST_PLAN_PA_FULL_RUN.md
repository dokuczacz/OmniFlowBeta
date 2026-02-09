# Test Plan: Full PA Run - Prompt Matrix & Tool Coverage

## Overview
This document outlines the comprehensive testing matrix for validating the backend fix (attach_file_handler/detach_file_handler) in a full PA (Personal Assistant) workflow with OpenAI integration.

## Testing Completed (Local/Static)

### ✅ Phase 1: Import & Module Loading
**Status:** PASSED  
**Evidence:** Local Python import tests

| Test Case | Status | Details |
|-----------|--------|---------|
| Import from shared.local_logger | ✅ PASS | Functions exist and are callable |
| Import in tool_call_handler | ✅ PASS | No NameError, module loads |
| OpenAI client import | ✅ PASS | OpenAI SDK available |
| Tool registry access | ✅ PASS | All 14 tools accessible |

### ✅ Phase 2: Function Behavior
**Status:** PASSED  
**Evidence:** Unit tests for attach/detach handlers

| Test Case | Status | Details |
|-----------|--------|---------|
| attach_file_handler("normal_name") | ✅ PASS | Handler created |
| detach_file_handler(handler) | ✅ PASS | Handler removed |
| detach_file_handler(None) | ✅ PASS | Handles None gracefully |
| Input sanitization (%, {}, \n) | ✅ PASS | Special chars sanitized |

### ✅ Phase 3: Security Testing
**Status:** PASSED  
**Evidence:** Security-focused unit tests

| Attack Vector | Status | Mitigation |
|---------------|--------|------------|
| Format string injection (%) | ✅ BLOCKED | Sanitized to _ |
| Brace injection ({}) | ✅ BLOCKED | Sanitized to _ |
| Log injection (newlines) | ✅ BLOCKED | Sanitized to _ |
| Control characters | ✅ BLOCKED | Whitelist validation |

---

## Testing Required (Runtime/OpenAI)

### ⏳ Phase 4: End-to-End PA Workflow
**Status:** PENDING  
**Requires:** OpenAI API key, Azure storage, runtime environment

#### Test Matrix: Tool Coverage (14 Tools)

| Tool Name | Test Scenario | Expected Prompt | Expected Tool Call | Status |
|-----------|---------------|-----------------|-------------------|--------|
| **get_current_time** | "What time is it?" | System: current time | `get_current_time()` | ⏳ PENDING |
| **list_blobs** | "Show my files" | System: list files | `list_blobs(user_id)` | ⏳ PENDING |
| **read_blob_file** | "Read file X" | System: read file | `read_blob_file(path)` | ⏳ PENDING |
| **read_many_blobs** | "Read files A, B, C" | System: batch read | `read_many_blobs([paths])` | ⏳ PENDING |
| **upload_data_or_file** | "Save this data" | System: upload | `upload_data_or_file(data)` | ⏳ PENDING |
| **update_data_entry** | "Update entry X" | System: update | `update_data_entry(id, data)` | ⏳ PENDING |
| **remove_data_entry** | "Delete entry X" | System: delete | `remove_data_entry(id)` | ⏳ PENDING |
| **get_filtered_data** | "Find items matching X" | System: filter | `get_filtered_data(filter)` | ⏳ PENDING |
| **dataset_search** | "Search datasets for Y" | System: search | `dataset_search(query)` | ⏳ PENDING |
| **oauth_email** | "Connect my email" | System: oauth | `oauth_email(action)` | ⏳ PENDING |
| **save_interaction** | Auto-triggered | System: save | `save_interaction(log)` | ⏳ PENDING |
| **wp7_indexer** | Semantic indexing | System: index | `wp7_indexer(content)` | ⏳ PENDING |
| **manage_files** | "Organize files" | System: manage | `manage_files(action)` | ⏳ PENDING |
| **custom_bridge** | Custom operations | System: bridge | `custom_bridge(op)` | ⏳ PENDING |

#### Test Matrix: WP6 Context Routing

| Scenario | Query Complexity | Expected Mode | Cache Efficiency | Status |
|----------|------------------|---------------|------------------|--------|
| Simple query | Low (<50) | FAST | >90% | ⏳ PENDING |
| Complex query | High (>50) | DEEP | >85% | ⏳ PENDING |
| Explicit FAST | N/A | FAST | >90% | ⏳ PENDING |
| Explicit DEEP | N/A | DEEP | >85% | ⏳ PENDING |
| User preference | Varies | Per setting | Varies | ⏳ PENDING |

#### Test Matrix: Error Scenarios

| Error Type | Test Case | Expected Behavior | Status |
|------------|-----------|-------------------|--------|
| Missing file | Read non-existent file | Structured error response | ⏳ PENDING |
| Invalid tool | Call unknown tool | Tool not found error | ⏳ PENDING |
| OAuth failure | Email without credentials | OAuth error message | ⏳ PENDING |
| Rate limit | Excessive requests | Rate limit handling | ⏳ PENDING |
| Network error | Azure storage down | Graceful degradation | ⏳ PENDING |

### ⏳ Phase 5: File Logging Validation
**Status:** PENDING  
**Requires:** Runtime execution

| Log Type | Trigger | Expected Output | Status |
|----------|---------|-----------------|--------|
| Request start | HTTP request received | Timestamp + user_id | ⏳ PENDING |
| Tool call | Any tool executed | Tool name + duration | ⏳ PENDING |
| OpenAI call | LLM interaction | Prompt tokens + cache hit | ⏳ PENDING |
| Request end | Response sent | Total duration + status | ⏳ PENDING |
| Error log | Exception occurs | Error type + stack trace | ⏳ PENDING |

### ⏳ Phase 6: Multi-User Isolation
**Status:** PENDING  
**Requires:** Multiple test users

| User Scenario | Test Case | Expected Result | Status |
|---------------|-----------|-----------------|--------|
| User A uploads file | POST with X-User-Id: A | File in users/A/ | ⏳ PENDING |
| User B uploads file | POST with X-User-Id: B | File in users/B/ | ⏳ PENDING |
| User A lists files | GET with X-User-Id: A | Only A's files | ⏳ PENDING |
| User B lists files | GET with X-User-Id: B | Only B's files | ⏳ PENDING |
| Cross-user access | A tries to read B's file | Access denied | ⏳ PENDING |

---

## Prompt Matrix Examples

### Example 1: Simple Query (FAST Mode)
```
User: "What time is it?"

Expected Flow:
1. tool_call_handler receives request
2. attach_file_handler("tool_call_handler") called
3. OpenAI prompt: [system context + tools + user message]
4. OpenAI response: Call get_current_time()
5. Execute tool
6. Return result to user
7. detach_file_handler() called
8. Log entry created in backend_debug.log

Expected Log Format:
2026-02-09 22:00:00 - tool_call_handler - root - INFO - Request start
2026-02-09 22:00:01 - tool_call_handler - root - INFO - Tool call: get_current_time
2026-02-09 22:00:01 - tool_call_handler - root - INFO - Request end (duration: 120ms)
```

### Example 2: Complex Query (DEEP Mode)
```
User: "Analyze my files from last week, categorize by topic, and summarize key themes"

Expected Flow:
1. tool_call_handler receives request
2. attach_file_handler("tool_call_handler") called
3. WP6 routing: Complexity score >50 → DEEP mode
4. OpenAI prompt: [system + semantic context + tools + user message]
5. Multiple tool calls:
   - list_blobs() to get files
   - read_many_blobs() to read content
   - dataset_search() for semantic context
6. Return analysis to user
7. detach_file_handler() called
8. Multiple log entries created

Expected Log Pattern:
- Request start
- Multiple tool calls logged
- Cache efficiency metrics
- Request end (longer duration)
```

### Example 3: Error Scenario
```
User: "Read file that_does_not_exist.txt"

Expected Flow:
1. tool_call_handler receives request
2. attach_file_handler("tool_call_handler") called
3. OpenAI decides to call read_blob_file("that_does_not_exist.txt")
4. Tool execution fails → structured error
5. Error logged with sanitized path
6. detach_file_handler() called
7. User receives error message

Expected Log:
2026-02-09 22:00:00 - tool_call_handler - root - INFO - Request start
2026-02-09 22:00:01 - tool_call_handler - root - ERROR - Tool call failed: read_blob_file
2026-02-09 22:00:01 - tool_call_handler - root - INFO - Request end (duration: 80ms)
```

---

## Validation Checklist

### Pre-Runtime Validation (Completed)
- [x] Code compiles without errors
- [x] Imports work correctly
- [x] Functions are callable
- [x] Unit tests pass
- [x] Security tests pass
- [x] CodeQL scan (0 alerts)

### Runtime Validation (Pending)
- [ ] Azure Functions starts successfully
- [ ] attach_file_handler creates log file
- [ ] Log entries written on each request
- [ ] Function name appears in logs
- [ ] detach_file_handler cleans up handlers
- [ ] No file descriptor leaks
- [ ] Log rotation works correctly

### OpenAI Integration Validation (Pending)
- [ ] OpenAI API calls succeed
- [ ] All 14 tools callable via prompts
- [ ] Tool responses processed correctly
- [ ] Error handling works
- [ ] Multi-turn conversations work
- [ ] Context building (WP6) works
- [ ] Semantic indexing (WP7) works

### Production Readiness (Pending)
- [ ] No logs on OpenAI dashboard (as reported by user)
- [ ] Full prompt matrix coverage
- [ ] Performance benchmarks meet targets
- [ ] Load testing passed
- [ ] Multi-user isolation verified
- [ ] Security audit passed

---

## Current Status Summary

**What's Fixed:**
✅ NameError resolved - code loads without crashing  
✅ Functions implemented with proper security  
✅ Static/unit tests pass  

**What's Pending:**
⏳ Runtime environment setup  
⏳ OpenAI API integration testing  
⏳ Full prompt matrix validation  
⏳ Production deployment  

**Next Steps:**
1. Set up local runtime environment (Azure Functions + Azurite)
2. Configure OpenAI API key
3. Run comprehensive test suite from this matrix
4. Document results with logs/screenshots
5. Deploy to production

---

## Notes

- This PR fixes the **import error** that prevented the code from loading
- **Runtime testing** requires environment setup beyond code changes
- The fix is **prerequisite** for OpenAI testing (code must load first)
- Full PA validation should be done in staging environment before production
