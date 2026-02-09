# Prompt Matrix: Complete Testing Guide for All Stages & Phases

## Overview
This document provides the complete prompt matrix for testing the PA (Personal Assistant) system across all stages, phases, and tools. Each section includes actual prompts, expected responses, and validation criteria.

---

## Stage 1: Basic Functionality (FAST Mode)

### Phase 1.1: Time & Date Tools

#### Test 1.1.1: get_current_time
**User Prompt:**
```
What time is it?
```

**Expected System Flow:**
1. Receive user message
2. attach_file_handler("tool_call_handler") called
3. OpenAI processes prompt with tools available
4. Tool call: `get_current_time()`
5. Return current time to user
6. detach_file_handler() called
7. Log entry created

**Expected Response:**
```
It's currently [HH:MM:SS] on [YYYY-MM-DD].
```

**Validation:**
- ✅ Response contains valid timestamp
- ✅ Tool called successfully
- ✅ Log shows "tool_call_handler" in format
- ✅ Request duration < 2s

#### Test 1.1.2: get_current_time (alternative phrasing)
**User Prompts:**
```
Tell me the current time
What's the time now?
Current time please
Time check
```

**Expected:** Same as 1.1.1

---

### Phase 1.2: File Listing Tools

#### Test 1.2.1: list_blobs - Basic
**User Prompt:**
```
Show me my files
```

**Expected System Flow:**
1. attach_file_handler("tool_call_handler")
2. Tool call: `list_blobs(user_id="test-user")`
3. Return file list
4. detach_file_handler()

**Expected Response:**
```
Here are your files:
1. document.txt (1.2 KB)
2. notes.md (3.4 KB)
3. data.json (5.6 KB)
```

**Validation:**
- ✅ Files listed with names and sizes
- ✅ User isolation maintained (only user's files)
- ✅ Log shows list_blobs call

#### Test 1.2.2: list_blobs - Filtered
**User Prompts:**
```
Show me my text files
List all PDF documents
What markdown files do I have?
Show files from last week
```

**Expected:** Filtered list based on criteria

---

### Phase 1.3: File Reading Tools

#### Test 1.3.1: read_blob_file - Single File
**User Prompt:**
```
Read the contents of notes.md
```

**Expected System Flow:**
1. attach_file_handler("tool_call_handler")
2. Tool call: `read_blob_file(path="users/test-user/notes.md")`
3. Return file contents
4. detach_file_handler()

**Expected Response:**
```
Here's the content of notes.md:
[file contents displayed]
```

**Validation:**
- ✅ Correct file read
- ✅ User can only read their own files
- ✅ Log shows read_blob_file call

#### Test 1.3.2: read_many_blobs - Multiple Files
**User Prompt:**
```
Read files: notes.md, document.txt, and data.json
```

**Expected System Flow:**
1. attach_file_handler("tool_call_handler")
2. Tool call: `read_many_blobs(paths=["users/test-user/notes.md", "users/test-user/document.txt", "users/test-user/data.json"])`
3. Return all file contents
4. detach_file_handler()

**Expected Response:**
```
Here are the contents of the requested files:

**notes.md:**
[content]

**document.txt:**
[content]

**data.json:**
[content]
```

**Validation:**
- ✅ All files read correctly
- ✅ Batch operation more efficient than multiple single reads
- ✅ Log shows read_many_blobs call

---

### Phase 1.4: File Writing Tools

#### Test 1.4.1: upload_data_or_file - Text Data
**User Prompt:**
```
Save this note: "Meeting tomorrow at 3pm with the team to discuss Q1 goals"
```

**Expected System Flow:**
1. attach_file_handler("tool_call_handler")
2. Tool call: `upload_data_or_file(data="Meeting tomorrow at 3pm with the team to discuss Q1 goals", filename="note_[timestamp].txt")`
3. File saved to user's directory
4. detach_file_handler()

**Expected Response:**
```
✅ Note saved successfully as note_20260209_223000.txt
```

**Validation:**
- ✅ File created in user's directory
- ✅ Content matches input
- ✅ Filename is unique/timestamped
- ✅ Log shows upload_data_or_file call

#### Test 1.4.2: upload_data_or_file - Structured Data
**User Prompt:**
```
Create a JSON file with my tasks: buy groceries, finish report, call dentist
```

**Expected System Flow:**
1. Tool call: `upload_data_or_file(data='{"tasks": ["buy groceries", "finish report", "call dentist"]}', filename="tasks.json")`

**Expected Response:**
```
✅ Created tasks.json with 3 tasks
```

---

### Phase 1.5: Data Management Tools

#### Test 1.5.1: update_data_entry
**User Prompt:**
```
Update my task "buy groceries" to "buy organic groceries"
```

**Expected System Flow:**
1. Tool call: `get_filtered_data(filter="buy groceries")`
2. Tool call: `update_data_entry(entry_id="xxx", new_data="buy organic groceries")`

**Expected Response:**
```
✅ Updated task successfully
```

#### Test 1.5.2: remove_data_entry
**User Prompt:**
```
Delete the task about calling dentist
```

**Expected System Flow:**
1. Tool call: `get_filtered_data(filter="call dentist")`
2. Tool call: `remove_data_entry(entry_id="xxx")`

**Expected Response:**
```
✅ Task deleted
```

---

## Stage 2: Complex Queries (DEEP Mode)

### Phase 2.1: Multi-Step Analysis

#### Test 2.1.1: File Analysis + Categorization
**User Prompt:**
```
Analyze all my files, categorize them by topic, and create a summary report
```

**Expected System Flow:**
1. attach_file_handler("tool_call_handler")
2. WP6 routing: Complexity > 50 → DEEP mode selected
3. Tool call: `list_blobs(user_id)`
4. Tool call: `read_many_blobs(paths=[...])`
5. Tool call: `dataset_search(query="semantic categorization")`
6. AI processes and categorizes
7. Tool call: `upload_data_or_file(data="[summary report]", filename="file_analysis.md")`
8. detach_file_handler()

**Expected Response:**
```
I've analyzed your files and created a summary report. Here's what I found:

**Categories:**
- Work documents (5 files)
- Personal notes (3 files)
- Data files (2 files)

**Summary:**
[Detailed analysis]

The full report has been saved as file_analysis.md
```

**Validation:**
- ✅ DEEP mode used (check logs)
- ✅ Multiple tools orchestrated
- ✅ Context includes semantic search
- ✅ Summary report created
- ✅ Cache efficiency > 85%

#### Test 2.1.2: Semantic Search + Synthesis
**User Prompt:**
```
Find all mentions of "project deadline" across my files, extract the dates, and tell me which deadlines are coming up this month
```

**Expected System Flow:**
1. DEEP mode activated
2. Tool call: `list_blobs(user_id)`
3. Tool call: `read_many_blobs(paths=[all_files])`
4. Tool call: `dataset_search(query="project deadline")`
5. Semantic analysis and date extraction
6. Calendar logic to filter this month

**Expected Response:**
```
I found 7 mentions of project deadlines. Here are the ones coming up this month:

1. **Project Alpha** - February 15, 2026 (6 days away)
   - Mentioned in: project_notes.md, meeting_summary.txt
   
2. **Report Submission** - February 28, 2026 (19 days away)
   - Mentioned in: work_tasks.json

3. **Client Review** - February 22, 2026 (13 days away)
   - Mentioned in: client_notes.md
```

**Validation:**
- ✅ DEEP mode used
- ✅ Semantic search performed
- ✅ Date extraction accurate
- ✅ Context from multiple files
- ✅ Synthesis coherent

---

### Phase 2.2: WP6 Context Routing

#### Test 2.2.1: Explicit FAST Mode
**User Prompt:**
```
[FAST] What time is it?
```

**Expected:**
- ✅ FAST mode forced (even for simple query)
- ✅ Cache efficiency > 90%

#### Test 2.2.2: Explicit DEEP Mode
**User Prompt:**
```
[DEEP] Show me my files
```

**Expected:**
- ✅ DEEP mode forced (even for simple query)
- ✅ Full semantic context loaded
- ✅ Cache efficiency > 85%

#### Test 2.2.3: Automatic Routing - Simple Query
**User Prompt:**
```
Hello
```

**Expected:**
- ✅ FAST mode auto-selected (complexity < 50)
- ✅ Quick response
- ✅ Cache efficiency > 90%

#### Test 2.2.4: Automatic Routing - Complex Query
**User Prompt:**
```
Review all my documents from the past month, identify common themes, create topic clusters, and generate a knowledge graph showing how different concepts relate to each other
```

**Expected:**
- ✅ DEEP mode auto-selected (complexity > 50)
- ✅ Semantic indexing used
- ✅ Multiple tool calls orchestrated
- ✅ Cache efficiency > 85%

---

## Stage 3: Tool-Specific Testing

### Phase 3.1: get_filtered_data

#### Test 3.1.1: Basic Filter
**User Prompt:**
```
Find all entries containing "urgent"
```

**Expected Tool Call:**
```python
get_filtered_data(filter="urgent")
```

#### Test 3.1.2: Complex Filter
**User Prompt:**
```
Find all tasks created last week that are marked high priority and haven't been completed
```

**Expected Tool Call:**
```python
get_filtered_data(
    filter={
        "created": "last_week",
        "priority": "high",
        "status": "incomplete"
    }
)
```

---

### Phase 3.2: dataset_search

#### Test 3.2.1: Semantic Search
**User Prompt:**
```
Search my knowledge base for information about machine learning algorithms
```

**Expected Tool Call:**
```python
dataset_search(query="machine learning algorithms")
```

**Expected Response:**
```
Found 12 relevant entries in your knowledge base:

1. **Neural Networks Overview** (Relevance: 0.95)
   - File: ml_notes.md
   - Content: [snippet]

2. **Decision Trees Explained** (Relevance: 0.87)
   - File: algorithms.txt
   - Content: [snippet]

[...]
```

#### Test 3.2.2: Cross-Reference Search
**User Prompt:**
```
Find connections between my notes on "Python programming" and "data analysis"
```

**Expected:**
- ✅ Semantic search for both topics
- ✅ Cross-reference analysis
- ✅ Relationship mapping

---

### Phase 3.3: oauth_email (Gmail Integration)

#### Test 3.3.1: OAuth Authorization
**User Prompt:**
```
Connect my Gmail account
```

**Expected System Flow:**
1. Tool call: `oauth_email(action="authorize")`
2. Return OAuth URL
3. User authorizes (external)
4. Callback received
5. Tokens stored

**Expected Response:**
```
Please authorize access to your Gmail account:
[OAuth URL]

Once authorized, I'll be able to help you manage your emails.
```

#### Test 3.3.2: Email Summary (Requires OAuth)
**User Prompt:**
```
Summarize my last 10 emails
```

**Expected System Flow:**
1. Check OAuth status
2. If authorized: Tool call: `oauth_email(action="list", count=10)`
3. Summarize emails

**Expected Response:**
```
Here's a summary of your last 10 emails:

1. **From:** john@example.com
   **Subject:** Meeting Reminder
   **Summary:** Meeting scheduled for tomorrow at 2pm

2. **From:** support@service.com
   **Subject:** Account Update
   **Summary:** Password changed successfully

[...]
```

---

### Phase 3.4: wp7_indexer (Semantic Indexing)

#### Test 3.4.1: Realtime Indexing
**User Prompt:**
```
Index this conversation for semantic search
```

**Expected System Flow:**
1. Tool call: `wp7_indexer(content=[conversation], mode="REALTIME")`
2. Semantic extraction
3. Index updated
4. Manifest generated

**Expected Response:**
```
✅ Conversation indexed successfully
- Extracted 15 semantic concepts
- Created 8 relationship links
- Updated knowledge graph
```

**Validation:**
- ✅ REALTIME mode used
- ✅ Cache efficiency 80-90%
- ✅ Index manifest updated

#### Test 3.4.2: Batch Indexing
**User Prompt:**
```
Index all my files for semantic search using batch mode
```

**Expected System Flow:**
1. Tool call: `list_blobs(user_id)`
2. Tool call: `read_many_blobs(paths=[...])`
3. Tool call: `wp7_indexer(content=[all_content], mode="BATCH")`
4. Batch processing
5. Index updated

**Expected Response:**
```
✅ Batch indexing complete
- Processed 25 files
- Extracted 347 concepts
- Created 189 relationships
- Cache efficiency: 78%
```

**Validation:**
- ✅ BATCH mode used
- ✅ Cache efficiency 60-80%
- ✅ All files indexed

---

### Phase 3.5: manage_files

#### Test 3.5.1: File Organization
**User Prompt:**
```
Organize my files by type into folders
```

**Expected Tool Call:**
```python
manage_files(
    action="organize",
    criteria="type",
    create_folders=True
)
```

**Expected Response:**
```
✅ Files organized successfully:
- Created folder: Documents (5 files)
- Created folder: Images (0 files)
- Created folder: Data (3 files)
- Created folder: Notes (7 files)
```

#### Test 3.5.2: File Cleanup
**User Prompt:**
```
Delete all files older than 90 days
```

**Expected Tool Call:**
```python
manage_files(
    action="cleanup",
    criteria={"age": ">90days"}
)
```

---

### Phase 3.6: custom_bridge

#### Test 3.6.1: Custom Operation
**User Prompt:**
```
Execute custom workflow: extract metadata from all PDFs
```

**Expected Tool Call:**
```python
custom_bridge(
    operation="extract_pdf_metadata",
    params={"file_types": ["pdf"]}
)
```

---

## Stage 4: Error Handling

### Phase 4.1: Missing Resources

#### Test 4.1.1: Non-existent File
**User Prompt:**
```
Read file_that_doesnt_exist.txt
```

**Expected System Flow:**
1. Tool call: `read_blob_file(path="users/test-user/file_that_doesnt_exist.txt")`
2. Error returned: FileNotFoundError
3. Graceful error handling

**Expected Response:**
```
❌ I couldn't find a file named "file_that_doesnt_exist.txt" in your storage.

Would you like me to:
1. Show you a list of available files?
2. Create a new file with that name?
```

**Validation:**
- ✅ Error handled gracefully
- ✅ Helpful suggestions provided
- ✅ Log shows sanitized error
- ✅ No stack trace exposed to user

#### Test 4.1.2: Invalid Tool Call
**User Prompt:**
```
[Inject invalid tool call]
```

**Expected:**
- ✅ Tool validation prevents invalid calls
- ✅ Error message clear
- ✅ System remains stable

---

### Phase 4.2: OAuth Errors

#### Test 4.2.1: OAuth Not Configured
**User Prompt:**
```
Check my emails
```

**Expected Response (if OAuth not configured):**
```
⚠️ Gmail integration is not set up yet.

To access your emails, you need to:
1. Configure Gmail OAuth credentials
2. Authorize access to your Gmail account

Would you like me to guide you through the setup?
```

**Validation:**
- ✅ Clear error message
- ✅ Helpful guidance
- ✅ No technical jargon

---

### Phase 4.3: Rate Limiting

#### Test 4.3.1: Excessive Requests
**User Prompts:** (sent in rapid succession)
```
What time is it?
What time is it?
What time is it?
[... 100 more times]
```

**Expected:**
- ✅ Rate limiting kicks in
- ✅ Graceful degradation
- ✅ Clear error message
- ✅ Retry-after indication

---

## Stage 5: Multi-User Isolation

### Phase 5.1: User A Operations

#### Test 5.1.1: User A Uploads File
**User:** user-a  
**Prompt:**
```
Save this: "User A's private data"
```

**Expected:**
- ✅ File saved to `users/user-a/`
- ✅ File not visible to other users

### Phase 5.2: User B Operations

#### Test 5.2.1: User B Uploads File
**User:** user-b  
**Prompt:**
```
Save this: "User B's private data"
```

**Expected:**
- ✅ File saved to `users/user-b/`
- ✅ File not visible to other users

### Phase 5.3: Cross-User Access Attempt

#### Test 5.3.1: User A Tries to Access User B's File
**User:** user-a  
**Prompt:**
```
Read users/user-b/private_file.txt
```

**Expected:**
- ✅ Access denied
- ✅ Error: "File not found" (not "Access denied" to prevent information disclosure)
- ✅ Log shows attempted access (security audit)

---

## Stage 6: Logging Verification

### Phase 6.1: Request Logging

#### Test 6.1.1: Simple Request Log
**User Prompt:**
```
What time is it?
```

**Expected Log Entries:**
```
2026-02-09 22:45:00 - tool_call_handler - root - INFO - Request start
2026-02-09 22:45:01 - tool_call_handler - tool_handler - INFO - Tool call: get_current_time
2026-02-09 22:45:01 - tool_call_handler - root - INFO - Request end (duration: 1234ms)
```

**Validation:**
- ✅ "tool_call_handler" appears in function name field
- ✅ All log entries present
- ✅ Timestamps accurate
- ✅ Duration calculated correctly

#### Test 6.1.2: Complex Request Log
**User Prompt:**
```
Analyze my files and create a summary
```

**Expected Log Entries:**
```
2026-02-09 22:45:00 - tool_call_handler - root - INFO - Request start
2026-02-09 22:45:01 - tool_call_handler - wp6 - INFO - Context mode: DEEP
2026-02-09 22:45:02 - tool_call_handler - tool_handler - INFO - Tool call: list_blobs
2026-02-09 22:45:03 - tool_call_handler - tool_handler - INFO - Tool call: read_many_blobs (5 files)
2026-02-09 22:45:04 - tool_call_handler - tool_handler - INFO - Tool call: dataset_search
2026-02-09 22:45:06 - tool_call_handler - openai - INFO - OpenAI call (tokens: 2500, cached: 2100)
2026-02-09 22:45:07 - tool_call_handler - tool_handler - INFO - Tool call: upload_data_or_file
2026-02-09 22:45:08 - tool_call_handler - root - INFO - Request end (duration: 8234ms)
```

**Validation:**
- ✅ All tool calls logged
- ✅ OpenAI cache hit logged
- ✅ DEEP mode logged
- ✅ Total duration tracked

---

## Validation Summary

### Required Checks for Each Test

1. **Functional:**
   - ✅ Correct tool(s) called
   - ✅ Expected response format
   - ✅ Data integrity maintained

2. **Logging:**
   - ✅ attach_file_handler called
   - ✅ "tool_call_handler" in log entries
   - ✅ detach_file_handler called
   - ✅ No file descriptor leaks

3. **Performance:**
   - ✅ Response time acceptable
   - ✅ Cache efficiency meets targets
   - ✅ No memory leaks

4. **Security:**
   - ✅ Input sanitized
   - ✅ User isolation maintained
   - ✅ Errors don't expose internals
   - ✅ No injection vulnerabilities

5. **Integration:**
   - ✅ OpenAI API calls successful
   - ✅ Azure storage operations work
   - ✅ All 14 tools accessible
   - ✅ WP6/WP7 routing correct

---

## Testing Checklist

### Pre-Test Setup
- [ ] OPENAI_API_KEY configured
- [ ] Backend running (localhost:7071)
- [ ] Azurite running
- [ ] Test user created
- [ ] Sample files uploaded

### Test Execution
- [ ] Run all Stage 1 tests (FAST mode)
- [ ] Run all Stage 2 tests (DEEP mode)
- [ ] Run all Stage 3 tests (tool-specific)
- [ ] Run all Stage 4 tests (error handling)
- [ ] Run all Stage 5 tests (multi-user)
- [ ] Verify all Stage 6 logs

### Post-Test Verification
- [ ] Check backend_debug.log for all entries
- [ ] Verify OpenAI dashboard shows API calls
- [ ] Confirm no errors in Azure storage
- [ ] Review cache efficiency metrics
- [ ] Validate all files created/modified
- [ ] Check for memory/file descriptor leaks

---

## Expected Results

### Success Criteria
- ✅ All prompts execute without errors
- ✅ All 14 tools functional
- ✅ FAST mode cache efficiency > 90%
- ✅ DEEP mode cache efficiency > 85%
- ✅ Multi-user isolation perfect
- ✅ Error handling graceful
- ✅ Logging complete and formatted correctly

### Metrics to Track
- **Total prompts tested:** 50+
- **Tools covered:** 14/14 (100%)
- **Phases covered:** 6/6 (100%)
- **Error scenarios:** 10+
- **Average response time:** < 3s
- **Cache hit rate:** > 85%
- **Test pass rate:** > 95%

---

## Next Steps

1. Execute all tests using provided scripts
2. Document results for each prompt
3. Create screenshots of responses
4. Generate performance metrics
5. Submit test report with evidence
