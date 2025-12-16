# Test script for all Azure Functions locally
# Run this in a separate PowerShell window while func host is running

$BaseUrl = "http://localhost:7071/api"
$Results = @()

function Test-Function {
    param(
        [string]$Name,
        [string]$Method,
        [string]$Endpoint,
        [hashtable]$Body = $null,
        [string]$QueryParams = ""
    )
    
    $Url = "$BaseUrl$Endpoint"
    if ($QueryParams) { $Url += "?$QueryParams" }
    
    try {
        $StartTime = Get-Date
        
        if ($Method -eq "GET") {
            $Response = Invoke-RestMethod -Uri $Url -Method GET -ErrorAction Stop
        } else {
            $JsonBody = $Body | ConvertTo-Json
            $Response = Invoke-RestMethod -Uri $Url -Method $Method -Body $JsonBody -ContentType "application/json" -ErrorAction Stop
        }
        
        $Duration = (Get-Date) - $StartTime
        $Status = "✅ PASS"
        $Message = "Success"
    }
    catch {
        $Duration = (Get-Date) - $StartTime
        $Status = "❌ FAIL"
        $Message = $_.Exception.Message
        $Response = $null
    }
    
    $Results += [PSCustomObject]@{
        Function = $Name
        Status = $Status
        Method = $Method
        Duration = "{0}ms" -f [int]$Duration.TotalMilliseconds
        Message = $Message
    }
    
    Write-Host "$Status $Name - $($Duration.TotalMilliseconds)ms"
    if ($Response) { Write-Host "  Response: $(($Response | ConvertTo-Json -Depth 1) -replace "`n", " ")" -ForegroundColor Gray }
    Write-Host ""
}

Write-Host "=== Testing All Azure Functions ===" -ForegroundColor Cyan
Write-Host ""

# 1. get_current_time
Test-Function -Name "get_current_time" -Method "GET" -Endpoint "/get_current_time"

# 2. list_blobs
Test-Function -Name "list_blobs" -Method "GET" -Endpoint "/list_blobs"

# 3. read_blob_file
Test-Function -Name "read_blob_file" -Method "GET" -Endpoint "/read_blob_file" -QueryParams "file_name=test2.json"

# 4. upload_data_or_file
Test-Function -Name "upload_data_or_file" -Method "POST" -Endpoint "/upload_data_or_file" -Body @{
    target_blob_name = "test_upload_$(Get-Date -Format 'HHmmss').json"
    file_content = @{ test = "data"; timestamp = (Get-Date -Format 'o') }
}

# 5. manage_files (list)
Test-Function -Name "manage_files (list)" -Method "POST" -Endpoint "/manage_files" -Body @{
    operation = "list"
}

# 6. add_new_data
Test-Function -Name "add_new_data" -Method "POST" -Endpoint "/add_new_data" -Body @{
    target_blob_name = "tasks.json"
    new_entry = @{ id = 1; title = "Test Task"; status = "open" }
}

# 7. get_filtered_data
Test-Function -Name "get_filtered_data" -Method "POST" -Endpoint "/get_filtered_data" -Body @{
    target_blob_name = "tasks.json"
    key = "status"
    value = "open"
}

# 8. update_data_entry
Test-Function -Name "update_data_entry" -Method "POST" -Endpoint "/update_data_entry" -Body @{
    target_blob_name = "tasks.json"
    find_key = "id"
    find_value = "1"
    update_key = "status"
    update_value = "completed"
}

# 9. remove_data_entry
Test-Function -Name "remove_data_entry" -Method "POST" -Endpoint "/remove_data_entry" -Body @{
    target_blob_name = "tasks.json"
    key_to_find = "id"
    value_to_find = "1"
}

# 10. save_interaction
Test-Function -Name "save_interaction" -Method "POST" -Endpoint "/save_interaction" -Body @{
    user_message = "Test message from user"
    assistant_response = "Test response from assistant"
    thread_id = "test-thread-001"
    tool_calls = @()
}

# 11. get_interaction_history
Test-Function -Name "get_interaction_history" -Method "GET" -Endpoint "/get_interaction_history" -QueryParams "limit=10&offset=0"

# 12. proxy_router
Test-Function -Name "proxy_router" -Method "POST" -Endpoint "/proxy_router" -Body @{
    action = "test_action"
    params = @{ test = "param" }
}

# 13. tool_call_handler
Test-Function -Name "tool_call_handler" -Method "POST" -Endpoint "/tool_call_handler" -Body @{
    message = "Test message"
    user_id = "test-user"
}

Write-Host ""
Write-Host "=== Test Summary ===" -ForegroundColor Cyan
Write-Host ""
$Results | Format-Table -AutoSize
Write-Host ""
$PassCount = ($Results | Where-Object { $_.Status -eq "✅ PASS" }).Count
$FailCount = ($Results | Where-Object { $_.Status -eq "❌ FAIL" }).Count
Write-Host "Total: $PassCount PASSED, $FailCount FAILED" -ForegroundColor $(if ($FailCount -eq 0) { "Green" } else { "Yellow" })
