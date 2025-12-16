
# Test script for all Azure Functions (local or Azure)
# Sources test_env.ps1 for environment config

. "$PSScriptRoot/test_env.ps1"
$Results = @()


# Calls tool_call_handler for each function, waits for agent answer, validates, then proceeds
function Test-ToolHandler {
    param(
        [string]$Name,
        [string]$ToolName,
        [hashtable]$ToolArgs = @{},
        [string]$UserId = "test_user_123"
    )
    $Url = "$BaseUrl/tool_call_handler?code=$FunctionKey"
    $Body = @{ tool_name = $ToolName; tool_arguments = $ToolArgs; user_id = $UserId } | ConvertTo-Json -Depth 5
    $Headers = $DefaultHeaders
    $StartTime = Get-Date
    try {
        $Response = Invoke-RestMethod -Uri $Url -Method POST -Body $Body -ContentType "application/json" -Headers $Headers -ErrorAction Stop
        $Duration = (Get-Date) - $StartTime
        $Status = if ($Response.status -eq "success") { "✅ PASS" } else { "❌ FAIL" }
        $Message = $Response.response
    } catch {
        $Duration = (Get-Date) - $StartTime
        $Status = "❌ FAIL"
        $Message = $_.Exception.Message
        $Response = $null
    }
    $Results += [PSCustomObject]@{
        Function = $Name
        Status = $Status
        Duration = "{0}ms" -f [int]$Duration.TotalMilliseconds
        Message = $Message
    }
    Write-Host "$Status $Name - $($Duration.TotalMilliseconds)ms"
    if ($Response) { Write-Host "  Response: $(($Response | ConvertTo-Json -Depth 1) -replace "`n", " ")" -ForegroundColor Gray }
    Write-Host ""
    Start-Sleep -Seconds 1 # Give agent a moment before next call
}

Write-Host "=== Testing All Azure Functions ===" -ForegroundColor Cyan
Write-Host ""


# 1. get_current_time
Test-ToolHandler -Name "get_current_time" -ToolName "get_current_time"

# 2. list_blobs
Test-ToolHandler -Name "list_blobs" -ToolName "list_blobs"

# 3. read_blob_file
Test-ToolHandler -Name "read_blob_file" -ToolName "read_blob_file" -ToolArgs @{ file_name = "test2.json" }

# 4. upload_data_or_file
Test-ToolHandler -Name "upload_data_or_file" -ToolName "upload_data_or_file" -ToolArgs @{ target_blob_name = "test_upload_$(Get-Date -Format 'HHmmss').json"; file_content = @{ test = "data"; timestamp = (Get-Date -Format 'o') } }

# 5. manage_files (list)
Test-ToolHandler -Name "manage_files (list)" -ToolName "manage_files" -ToolArgs @{ operation = "list" }

# 6. add_new_data
Test-ToolHandler -Name "add_new_data" -ToolName "add_new_data" -ToolArgs @{ target_blob_name = "tasks.json"; new_entry = @{ id = 1; title = "Test Task"; status = "open" } }

# 7. get_filtered_data
Test-ToolHandler -Name "get_filtered_data" -ToolName "get_filtered_data" -ToolArgs @{ target_blob_name = "tasks.json"; key = "status"; value = "open" }

# 8. update_data_entry
Test-ToolHandler -Name "update_data_entry" -ToolName "update_data_entry" -ToolArgs @{ target_blob_name = "tasks.json"; find_key = "id"; find_value = "1"; update_key = "status"; update_value = "completed" }

# 9. remove_data_entry
Test-ToolHandler -Name "remove_data_entry" -ToolName "remove_data_entry" -ToolArgs @{ target_blob_name = "tasks.json"; key_to_find = "id"; value_to_find = "1" }

# 10. save_interaction
Test-ToolHandler -Name "save_interaction" -ToolName "save_interaction" -ToolArgs @{ user_message = "Test message from user"; assistant_response = "Test response from assistant"; thread_id = "test-thread-001"; tool_calls = @() }

# 11. get_interaction_history
Test-ToolHandler -Name "get_interaction_history" -ToolName "get_interaction_history" -ToolArgs @{ limit = 10; offset = 0 }

# 12. proxy_router
Test-ToolHandler -Name "proxy_router" -ToolName "proxy_router" -ToolArgs @{ action = "test_action"; params = @{ test = "param" } }

# 13. tool_call_handler
Test-ToolHandler -Name "tool_call_handler" -ToolName "tool_call_handler" -ToolArgs @{ message = "Test message"; user_id = "test-user" }

Write-Host ""
Write-Host "=== Test Summary ===" -ForegroundColor Cyan
Write-Host ""
$Results | Format-Table -AutoSize
Write-Host ""
$PassCount = ($Results | Where-Object { $_.Status -eq "✅ PASS" }).Count
$FailCount = ($Results | Where-Object { $_.Status -eq "❌ FAIL" }).Count
Write-Host "Total: $PassCount PASSED, $FailCount FAILED" -ForegroundColor $(if ($FailCount -eq 0) { "Green" } else { "Yellow" })
