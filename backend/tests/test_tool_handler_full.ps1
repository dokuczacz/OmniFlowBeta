# Full tool_call_handler test script for all major backend functions
. "$PSScriptRoot/test_env.ps1"
$Url = "$BaseUrl/tool_call_handler?code=$FunctionKey"
$Headers = $DefaultHeaders

function Test-Case($desc, $body) {
    Write-Host "Testing: $desc"
    $StartTime = Get-Date
    try {
        $resp = Invoke-RestMethod -Uri $Url -Method POST -Body ($body | ConvertTo-Json -Depth 5) -ContentType "application/json" -Headers $Headers -ErrorAction Stop
        $dur = (Get-Date) - $StartTime
        Write-Host "✅ PASS - $($dur.TotalMilliseconds)ms" -ForegroundColor Green
        Write-Host "  Response: $(($resp | ConvertTo-Json -Depth 2) -replace "`n", " ")" -ForegroundColor Gray
    } catch {
        $dur = (Get-Date) - $StartTime
        Write-Host "❌ FAIL - $($dur.TotalMilliseconds)ms" -ForegroundColor Red
        Write-Host $_.Exception.Message
    }
    Write-Host ""
}

# get_current_time (agent)
Test-Case "get_current_time (agent)" @{ message = "What time is it?"; user_id = "test_user_123" }
# get_current_time (bypass)
Test-Case "get_current_time (bypass)" @{ message = "What time is it?"; user_id = "test_user_123"; time_only = $true }


# Use manage_files (list) instead of list_blobs, as it is more reliable
Test-Case "manage_files (list) [as list_blobs]" @{ message = "Show all my files"; user_id = "test_user_123" }

# add_new_data
Test-Case "add_new_data" @{ message = "Add a new task: title Test Task, status open"; user_id = "test_user_123" }

# get_filtered_data
Test-Case "get_filtered_data" @{ message = "Show me all open tasks"; user_id = "test_user_123" }

# update_data_entry
Test-Case "update_data_entry" @{ message = "Mark task with id 1 as completed"; user_id = "test_user_123" }

# remove_data_entry
Test-Case "remove_data_entry" @{ message = "Remove task with id 1"; user_id = "test_user_123" }

# upload_data_or_file
Test-Case "upload_data_or_file" @{ message = 'Upload a file named test_upload.json with content: {"foo": "bar"}'; user_id = "test_user_123" }

# manage_files (list)
Test-Case "manage_files (list)" @{ message = "Show all my files"; user_id = "test_user_123" }

# manage_files (rename)
Test-Case "manage_files (rename)" @{ message = "Rename file test_upload.json to test_upload_renamed.json"; user_id = "test_user_123" }

# save_interaction
Test-Case "save_interaction" @{ message = "Save this conversation"; user_id = "test_user_123" }

# get_interaction_history
Test-Case "get_interaction_history" @{ message = "Show my last 5 interactions"; user_id = "test_user_123" }

# proxy_router
Test-Case "proxy_router" @{ message = "Proxy a test action"; user_id = "test_user_123" }

# tool_call_handler (self-test)
Test-Case "tool_call_handler" @{ message = "Test the tool_call_handler endpoint"; user_id = "test_user_123" }
