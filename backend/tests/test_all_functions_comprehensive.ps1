# Comprehensive Test for ALL 13 Azure Functions with User Isolation
# Tests all functions to ensure they're working correctly with user isolation


Write-Host "=== COMPREHENSIVE TEST: ALL 13 FUNCTIONS ===" -ForegroundColor Cyan
Write-Host "Testing user isolation across entire backend..." -ForegroundColor Cyan

. "$PSScriptRoot/test_env.ps1"
$testResults = @()
$aliceUserId = "alice_test_comprehensive"
$bobUserId = "bob_test_comprehensive"

# Helper function to record test results
function Record-Test {
    param($FunctionName, $TestName, $Passed, $Details = "")
    $testResults += [PSCustomObject]@{
        Function = $FunctionName
        Test = $TestName
        Passed = $Passed
        Details = $Details
    }
    if ($Passed) {
        Write-Host "  ✅ $TestName" -ForegroundColor Green
    } else {
        Write-Host "  ❌ $TestName - $Details" -ForegroundColor Red
    }
}

# ==================================================

# Helper to build URL
function Get-ApiUrl($endpoint, $queryParams = "") {
    $url = "$BaseUrl$endpoint"
    if ($queryParams) { $url += "?$queryParams" }
    return $url
}

# Helper to merge headers
function Merge-Headers($extra) {
    $h = @{}
    if ($DefaultHeaders) { $h += $DefaultHeaders }
    if ($extra) { $h += $extra }
    return $h
}

# TEST 1: get_current_time (stateless, no user isolation needed)
# ==================================================
Write-Host "`n[1/13] Testing get_current_time..." -ForegroundColor Yellow
try {
    $time = Invoke-RestMethod -Uri (Get-ApiUrl "/get_current_time") -Method Get -Headers (Merge-Headers $null)
    $passed = $time.current_time_utc -and $time.current_time_utc.Length -gt 0
    Record-Test "get_current_time" "Returns UTC time" $passed
} catch {
    Record-Test "get_current_time" "Returns UTC time" $false $_.Exception.Message
}

# ==================================================
# TEST 2: upload_data_or_file
# ==================================================
Write-Host "`n[2/13] Testing upload_data_or_file..." -ForegroundColor Yellow
try {
    $aliceUpload = @{
        target_blob_name = "test_data.json"
        file_content = @(@{id="A1"; data="Alice data"})
    } | ConvertTo-Json -Depth 5
    
    $result = Invoke-RestMethod -Uri (Get-ApiUrl "/upload_data_or_file") `
        -Method Post -Body $aliceUpload -ContentType "application/json" `
        -Headers (Merge-Headers @{"x-user-id"=$aliceUserId})
    
    $passed = $result.storage_location -like "*$aliceUserId*"
    Record-Test "upload_data_or_file" "User isolation in path" $passed
} catch {
    Record-Test "upload_data_or_file" "User isolation in path" $false $_.Exception.Message
}

# ==================================================
# TEST 3: read_blob_file
# ==================================================
Write-Host "`n[3/13] Testing read_blob_file..." -ForegroundColor Yellow
try {
    $result = Invoke-RestMethod -Uri (Get-ApiUrl "/read_blob_file" "file_name=test_data.json") `
        -Method Get -Headers (Merge-Headers @{"x-user-id"=$aliceUserId})
    
    $passed = $result.user_id -eq $aliceUserId -and $result.data[0].id -eq "A1"
    Record-Test "read_blob_file" "Reads user-namespaced file" $passed
} catch {
    Record-Test "read_blob_file" "Reads user-namespaced file" $false $_.Exception.Message
}

# ==================================================
# TEST 4: add_new_data
# ==================================================
Write-Host "`n[4/13] Testing add_new_data..." -ForegroundColor Yellow
try {
    $addBody = @{
        target_blob_name = "test_data.json"
        new_entry = @{id="A2"; data="Alice new entry"}
    } | ConvertTo-Json -Depth 5
    
    $result = Invoke-RestMethod -Uri (Get-ApiUrl "/add_new_data") `
        -Method Post -Body $addBody -ContentType "application/json" `
        -Headers (Merge-Headers @{"x-user-id"=$aliceUserId})
    
    $passed = $result.user_id -eq $aliceUserId -and $result.entry_count -eq 2
    Record-Test "add_new_data" "Appends to user file" $passed
} catch {
    Record-Test "add_new_data" "Appends to user file" $false $_.Exception.Message
}

# ==================================================
# TEST 5: get_filtered_data
# ==================================================
Write-Host "`n[5/13] Testing get_filtered_data..." -ForegroundColor Yellow
try {
    $filterBody = @{
        target_blob_name = "test_data.json"
        filter_key = "id"
        filter_value = "A1"
    } | ConvertTo-Json -Depth 5
    
    $result = Invoke-RestMethod -Uri (Get-ApiUrl "/get_filtered_data") `
        -Method Post -Body $filterBody -ContentType "application/json" `
        -Headers (Merge-Headers @{"x-user-id"=$aliceUserId})
    
    $passed = $result.user_id -eq $aliceUserId -and $result.filtered_count -eq 1
    Record-Test "get_filtered_data" "Filters user data" $passed
} catch {
    Record-Test "get_filtered_data" "Filters user data" $false $_.Exception.Message
}

# ==================================================
# TEST 6: update_data_entry
# ==================================================
Write-Host "`n[6/13] Testing update_data_entry..." -ForegroundColor Yellow
try {
    $updateBody = @{
        target_blob_name = "test_data.json"
        find_key = "id"
        find_value = "A1"
        update_key = "status"
        update_value = "updated"
    } | ConvertTo-Json -Depth 5
    
    $result = Invoke-RestMethod -Uri (Get-ApiUrl "/update_data_entry") `
        -Method Post -Body $updateBody -ContentType "application/json" `
        -Headers (Merge-Headers @{"x-user-id"=$aliceUserId})
    
    $passed = $result.user_id -eq $aliceUserId -and $result.updated_value -eq "updated"
    Record-Test "update_data_entry" "Updates user entry" $passed
} catch {
    Record-Test "update_data_entry" "Updates user entry" $false $_.Exception.Message
}

# ==================================================
# TEST 7: remove_data_entry
# ==================================================
Write-Host "`n[7/13] Testing remove_data_entry..." -ForegroundColor Yellow
try {
    $removeBody = @{
        target_blob_name = "test_data.json"
        key_to_find = "id"
        value_to_find = "A2"
    } | ConvertTo-Json -Depth 5
    
    $result = Invoke-RestMethod -Uri (Get-ApiUrl "/remove_data_entry") `
        -Method Post -Body $removeBody -ContentType "application/json" `
        -Headers (Merge-Headers @{"x-user-id"=$aliceUserId})
    
    $passed = $result.user_id -eq $aliceUserId -and $result.deleted_count -eq 1
    Record-Test "remove_data_entry" "Removes user entry" $passed
} catch {
    Record-Test "remove_data_entry" "Removes user entry" $false $_.Exception.Message
}

# ==================================================
# TEST 8: list_blobs
# ==================================================
Write-Host "`n[8/13] Testing list_blobs..." -ForegroundColor Yellow
try {
    $result = Invoke-RestMethod -Uri (Get-ApiUrl "/list_blobs") `
        -Method Get -Headers (Merge-Headers @{"x-user-id"=$aliceUserId})
    
    $passed = $result.user_id -eq $aliceUserId -and $result.blobs -contains "test_data.json"
    Record-Test "list_blobs" "Lists user blobs only" $passed
} catch {
    Record-Test "list_blobs" "Lists user blobs only" $false $_.Exception.Message
}

# ==================================================
# TEST 9: manage_files (list operation)
# ==================================================
Write-Host "`n[9/13] Testing manage_files (list)..." -ForegroundColor Yellow
try {
    $listBody = @{operation = "list"} | ConvertTo-Json
    
    $result = Invoke-RestMethod -Uri (Get-ApiUrl "/manage_files") `
        -Method Post -Body $listBody -ContentType "application/json" `
        -Headers (Merge-Headers @{"x-user-id"=$aliceUserId})
    
    $passed = $result.user_id -eq $aliceUserId -and $result.files -contains "test_data.json"
    Record-Test "manage_files" "Lists user files" $passed
} catch {
    Record-Test "manage_files" "Lists user files" $false $_.Exception.Message
}

# ==================================================
# TEST 10: manage_files (rename operation)
# ==================================================
Write-Host "`n[10/13] Testing manage_files (rename)..." -ForegroundColor Yellow
try {
    $renameBody = @{
        operation = "rename"
        source_name = "test_data.json"
        target_name = "renamed_data.json"
    } | ConvertTo-Json
    
    $result = Invoke-RestMethod -Uri (Get-ApiUrl "/manage_files") `
        -Method Post -Body $renameBody -ContentType "application/json" `
        -Headers (Merge-Headers @{"x-user-id"=$aliceUserId})
    
    $passed = $result.user_id -eq $aliceUserId -and $result.operation -eq "rename"
    Record-Test "manage_files" "Renames user file" $passed
} catch {
    Record-Test "manage_files" "Renames user file" $false $_.Exception.Message
}

# ==================================================
# TEST 11: save_interaction
# ==================================================
Write-Host "`n[11/13] Testing save_interaction..." -ForegroundColor Yellow
try {
    $interactionBody = @{
        user_message = "Test message"
        assistant_response = "Test response"
        thread_id = "test_thread_123"
        tool_calls = @()
        metadata = @{source = "comprehensive_test"}
    } | ConvertTo-Json -Depth 5
    
    $result = Invoke-RestMethod -Uri (Get-ApiUrl "/save_interaction") `
        -Method Post -Body $interactionBody -ContentType "application/json" `
        -Headers (Merge-Headers @{"x-user-id"=$aliceUserId})
    
    $passed = $result.user_id -eq $aliceUserId -and $result.interaction_id
    Record-Test "save_interaction" "Saves user interaction" $passed
} catch {
    Record-Test "save_interaction" "Saves user interaction" $false $_.Exception.Message
}

# ==================================================
# TEST 12: get_interaction_history
# ==================================================
Write-Host "`n[12/13] Testing get_interaction_history..." -ForegroundColor Yellow
try {
    $result = Invoke-RestMethod -Uri (Get-ApiUrl "/get_interaction_history" "limit=10") `
        -Method Get -Headers (Merge-Headers @{"x-user-id"=$aliceUserId})
    
    $passed = $result.user_id -eq $aliceUserId -and $result.total_count -ge 1
    Record-Test "get_interaction_history" "Retrieves user history" $passed
} catch {
    Record-Test "get_interaction_history" "Retrieves user history" $false $_.Exception.Message
}

# ==================================================
# TEST 13: Cross-user isolation check
# ==================================================
Write-Host "`n[13/13] Testing cross-user isolation (Bob vs Alice)..." -ForegroundColor Yellow
try {
    # Bob tries to list blobs
    $bobResult = Invoke-RestMethod -Uri (Get-ApiUrl "/list_blobs") `
        -Method Get -Headers (Merge-Headers @{"x-user-id"=$bobUserId})
    
    # Bob should not see Alice's renamed_data.json
    $bobSeesAliceFile = $bobResult.blobs -contains "renamed_data.json"
    $passed = -not $bobSeesAliceFile -and $bobResult.user_id -eq $bobUserId
    
    if ($passed) {
        Record-Test "cross-user-isolation" "Bob cannot see Alice's files" $true
    } else {
        Record-Test "cross-user-isolation" "Bob cannot see Alice's files" $false "Bob sees Alice's files!"
    }
} catch {
    Record-Test "cross-user-isolation" "Bob cannot see Alice's files" $false $_.Exception.Message
}

# ==================================================
# FINAL SUMMARY
# ==================================================
Write-Host "`n=================================================" -ForegroundColor Cyan
Write-Host "FINAL RESULTS" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

$totalTests = $testResults.Count
$passedTests = ($testResults | Where-Object {$_.Passed}).Count
$failedTests = $totalTests - $passedTests

Write-Host "`nTotal Tests: $totalTests" -ForegroundColor White
Write-Host "Passed: $passedTests" -ForegroundColor Green
Write-Host "Failed: $failedTests" -ForegroundColor Red

if ($failedTests -eq 0) {
    Write-Host "`n🎉 ALL TESTS PASSED! Backend is fully operational with user isolation! 🎉" -ForegroundColor Green
} else {
    Write-Host "`n⚠️  Some tests failed. Review details above." -ForegroundColor Yellow
    Write-Host "`nFailed Tests:" -ForegroundColor Red
    $testResults | Where-Object {-not $_.Passed} | ForEach-Object {
        Write-Host "  - [$($_.Function)] $($_.Test): $($_.Details)" -ForegroundColor Red
    }
}

Write-Host "`n=================================================" -ForegroundColor Cyan
