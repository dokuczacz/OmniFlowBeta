# OpenAI Integration Testing Guide

This directory contains test scripts to validate the `attach_file_handler`/`detach_file_handler` fix with actual OpenAI API calls and backend requests.

## Test Scripts

### 1. `test_openai_integration.py` - Local Integration Tests
Tests the fix without requiring the full backend to be running.

**What it tests:**
- ✅ Import verification (no NameError)
- ✅ OpenAI client initialization
- ✅ File handler attach/detach functionality
- ✅ Tool registry accessibility
- ✅ Basic OpenAI API call
- ✅ Log file creation

**Prerequisites:**
```bash
export OPENAI_API_KEY="your-key-here"
pip install openai azure-functions azure-storage-blob requests
```

**Run:**
```bash
python test_openai_integration.py
```

**Expected Output:**
```
======================================================================
OPENAI INTEGRATION TEST SUITE
======================================================================

Test 1: Import Verification
✅ PASS: Import attach_file_handler/detach_file_handler
✅ PASS: Import tool_call_handler module
✅ PASS: Import OpenAI client

Test 2: Environment Configuration
✅ PASS: OPENAI_API_KEY configured
  Key prefix: sk-proj-ab...
✅ PASS: Azure storage configured
  Using Azurite (local development storage)

... (more tests)

TEST SUMMARY
Duration: 2.45s
Passed: 12
Failed: 0
Warnings: 1

🎉 ALL TESTS PASSED!
```

### 2. `test_e2e_backend.py` - End-to-End Backend Tests
Tests the complete workflow with HTTP requests to the running backend.

**What it tests:**
- ✅ Backend health (connectivity)
- ✅ Simple tool call (get_current_time)
- ✅ Complex tool call (DEEP mode with multiple tools)
- ✅ Error handling (graceful failures)
- ✅ Log file verification (file_handler working)

**Prerequisites:**
1. Start Azurite (local storage):
```bash
azurite --silent --location .azurite --debug .azurite/debug.log
```

2. Start backend:
```bash
cd backend
func start
```

3. Configure environment:
```bash
export OPENAI_API_KEY="your-key-here"
```

**Run:**
```bash
python test_e2e_backend.py
```

**With custom backend URL:**
```bash
python test_e2e_backend.py --base-url http://localhost:7071
```

**Expected Output:**
```
======================================================================
END-TO-END BACKEND TEST SUITE
======================================================================
Started at: 2026-02-09T22:30:00.000Z
Backend URL: http://localhost:7071

Test 1: Backend Health Check
✅ PASS: Backend health check (0.12s)
  Backend responding (status: 200)

Test 2: Simple Tool Call - get_current_time
✅ PASS: Simple tool call (get_current_time) (1.23s)
  Response received: {"result": "2026-02-09 22:30:01"}...
  Check backend_debug.log for 'tool_call_handler' entries

Test 3: Complex Tool Call - DEEP Mode
✅ PASS: Complex tool call (DEEP mode) (3.45s)
  Response received in 3.45s

Test 4: Error Handling
✅ PASS: Error handling (invalid request) (0.15s)
  Backend returned error gracefully (status: 400)

Test 5: Log File Verification
✅ PASS: Log file created
  backend_debug.log exists (2048 bytes)
  Total log entries: 42
  Entries with 'tool_call_handler': 8
  Latest entry:
    2026-02-09 22:30:03 - tool_call_handler - root - INFO - Request end (duration: 1234ms)

E2E TEST SUMMARY
Duration: 5.23s
Passed: 5/5
Failed: 0/5

🎉 ALL E2E TESTS PASSED!
```

## Verification Checklist

After running both test scripts, verify:

### Import Fix (PRIMARY GOAL)
- [ ] No NameError when importing `tool_call_handler`
- [ ] `attach_file_handler` and `detach_file_handler` are callable
- [ ] Functions work without crashes

### OpenAI Integration
- [ ] OpenAI API calls succeed
- [ ] Tool orchestration works
- [ ] File handler is attached during requests
- [ ] File handler is detached after requests

### Logging Verification
- [ ] `backend_debug.log` is created
- [ ] Log entries contain `tool_call_handler` function name
- [ ] Log format matches expected pattern:
  ```
  YYYY-MM-DD HH:MM:SS - tool_call_handler - logger_name - LEVEL - message
  ```
- [ ] Logs show request start/end
- [ ] Logs show tool calls
- [ ] No file descriptor leaks

### Tool Coverage (Full PA Run)
Run manual tests for each of the 14 tools using the UI or API:

1. **get_current_time**: "What time is it?"
2. **list_blobs**: "Show my files"
3. **read_blob_file**: "Read file X"
4. **read_many_blobs**: "Read files A, B, and C"
5. **upload_data_or_file**: "Save this data: {content}"
6. **update_data_entry**: "Update entry X with Y"
7. **remove_data_entry**: "Delete entry X"
8. **get_filtered_data**: "Find items matching X"
9. **dataset_search**: "Search datasets for Y"
10. **oauth_email**: "Connect my email"
11. **save_interaction**: (Auto-triggered)
12. **wp7_indexer**: (Semantic indexing)
13. **manage_files**: "Organize my files"
14. **custom_bridge**: (Custom operations)

## Troubleshooting

### "Cannot connect to backend"
- Ensure backend is running: `cd backend && func start`
- Check URL: default is `http://localhost:7071`
- Check Azurite is running: `azurite --silent --location .azurite`

### "OPENAI_API_KEY not set"
```bash
export OPENAI_API_KEY="sk-proj-your-key-here"
```

Or create `backend/local.settings.json`:
```json
{
  "IsEncrypted": false,
  "Values": {
    "OPENAI_API_KEY": "sk-proj-your-key-here",
    "AZURE_STORAGE_CONNECTION_STRING": "UseDevelopmentStorage=true",
    ...
  }
}
```

### "No log entries found"
- Check if backend is writing logs
- Verify file permissions on `backend_debug.log`
- Check if `attach_file_handler` is being called (add debug prints)

### "Import errors"
```bash
pip install openai azure-functions azure-storage-blob requests pydantic
```

## Test Results Documentation

After running tests, document results in your PR:

1. **Screenshot of test output** showing all tests passing
2. **Log file excerpt** showing `tool_call_handler` entries
3. **OpenAI dashboard** showing API calls (if available)
4. **Tool coverage matrix** from manual testing

## Next Steps

1. Run `test_openai_integration.py` to verify the fix locally
2. Start backend and run `test_e2e_backend.py` for full workflow
3. Check `backend_debug.log` for proper logging
4. Run manual tool tests using the UI
5. Document results and commit evidence

## Reference

See `TEST_PLAN_PA_FULL_RUN.md` for the complete testing matrix including:
- Detailed prompt examples for each tool
- WP6 context routing scenarios (FAST/DEEP)
- Error handling test cases
- Multi-user isolation tests
- Production readiness checklist
