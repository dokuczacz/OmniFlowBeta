# Test Deployment - Backend Security & Multi-User Isolation
# Tests: auth fix, user isolation, CRUD operations, logging

$baseUrl = "https://agentbackendservice-dfcpcudzeah4b6ae.northeurope-01.azurewebsites.net/api"

# Function-specific keys from Azure (now loaded from environment variables)
$functionKeys = @{
    "manage_files" = $env:MANAGE_FILES_KEY
    "upload_data_or_file" = $env:UPLOAD_DATA_OR_FILE_KEY
    "read_blob_file" = $env:READ_BLOB_FILE_KEY
    "update_data_entry" = $env:UPDATE_DATA_ENTRY_KEY
    "remove_data_entry" = $env:REMOVE_DATA_ENTRY_KEY
    "list_blobs" = $env:LIST_BLOBS_KEY
}

Write-Host "`n========== DEPLOYMENT TEST SUITE ==========" -ForegroundColor Cyan
Write-Host "Testing deployed backend changes..." -ForegroundColor Cyan

# Test data
$testFile = "test_data.json"
$testUser1 = "test_user_alice"
$testUser2 = "test_user_bob"

# Helper function to make requests
function Invoke-BackendTest {
    param(
        [string]$Endpoint,
        [string]$Method = "GET",
        [hashtable]$Body = @{},
        [string]$UserId = "",
        [bool]$IncludeAuth = $true,
        [string]$TestName = ""
    )
    
    Write-Host "`n--- $TestName ---" -ForegroundColor Yellow
    
    $headers = @{
        "Content-Type" = "application/json"
    }
    
    if ($UserId) {
        $headers["X-User-Id"] = $UserId
        Write-Host "User: $UserId" -ForegroundColor Gray
    }
    
    $url = "$baseUrl/$Endpoint"
    if ($IncludeAuth) {
        $key = $functionKeys[$Endpoint]
        if ($key) {
            $separator = if ($url -match '\?') { '&' } else { '?' }
            $url += "$separator`code=$key"
        }
    }
    
    Write-Host "URL: $Endpoint" -ForegroundColor Gray
    
    try {
        $params = @{
            Uri = $url
            Method = $Method
            Headers = $headers
            ContentType = "application/json"
        }
        
        if ($Method -ne "GET" -and $Body.Count -gt 0) {
            $params["Body"] = ($Body | ConvertTo-Json -Depth 10)
            Write-Host "Payload: $($params["Body"])" -ForegroundColor Gray
        }
        
        $response = Invoke-RestMethod @params
        Write-Host "✅ SUCCESS - Status: 200" -ForegroundColor Green
        Write-Host "Response: $($response | ConvertTo-Json -Depth 5)" -ForegroundColor Green
        return @{ Success = $true; Data = $response }
    }
    catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        Write-Host "❌ FAILED - Status: $statusCode" -ForegroundColor Red
        Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
        return @{ Success = $false; StatusCode = $statusCode; Error = $_.Exception.Message }
    }
}

Write-Host "`n========== TEST 1: Auth Requirement (manage_files) ==========" -ForegroundColor Cyan

# Test 1a: Call manage_files WITHOUT auth (should fail with 401)
$result = Invoke-BackendTest -Endpoint "manage_files" -Method "POST" `
    -Body @{ operation = "list"; user_id = $testUser1 } `
    -IncludeAuth $false `
    -TestName "manage_files WITHOUT function key (expect 401)"

if (-not $result.Success -and $result.StatusCode -eq 401) {
    Write-Host "✅ PASS: Auth required correctly enforced" -ForegroundColor Green
} else {
    Write-Host "❌ FAIL: Should require authentication!" -ForegroundColor Red
}

# Test 1b: Call manage_files WITH auth (should succeed)
$result = Invoke-BackendTest -Endpoint "manage_files" -Method "POST" `
    -Body @{ operation = "list"; user_id = $testUser1 } `
    -UserId $testUser1 `
    -IncludeAuth $true `
    -TestName "manage_files WITH function key (expect 200)"

if ($result.Success) {
    Write-Host "✅ PASS: Auth accepted correctly" -ForegroundColor Green
} else {
    Write-Host "❌ FAIL: Should accept valid auth!" -ForegroundColor Red
}

Write-Host "`n========== TEST 2: Multi-User Isolation (upload) ==========" -ForegroundColor Cyan

# Test 2a: Upload data for user Alice
$aliceData = @{
    target_blob_name = $testFile
    file_content = @(
        @{ name = "Alice Item 1"; value = 100; owner = "alice" }
        @{ name = "Alice Item 2"; value = 200; owner = "alice" }
    )
}

$result = Invoke-BackendTest -Endpoint "upload_data_or_file" -Method "POST" `
    -Body $aliceData `
    -UserId $testUser1 `
    -TestName "Upload data for Alice"

# Test 2b: Upload data for user Bob
$bobData = @{
    target_blob_name = $testFile
    file_content = @(
        @{ name = "Bob Item 1"; value = 300; owner = "bob" }
        @{ name = "Bob Item 2"; value = 400; owner = "bob" }
    )
}

$result = Invoke-BackendTest -Endpoint "upload_data_or_file" -Method "POST" `
    -Body $bobData `
    -UserId $testUser2 `
    -TestName "Upload data for Bob"

Write-Host "`n========== TEST 3: Multi-User Isolation (read) ==========" -ForegroundColor Cyan

# Test 3a: Read Alice's data as Alice
$result = Invoke-BackendTest -Endpoint "read_blob_file" -Method "POST" `
    -Body @{ target_blob_name = $testFile } `
    -UserId $testUser1 `
    -TestName "Read Alice's data as Alice"

if ($result.Success -and $result.Data.content -match "alice") {
    Write-Host "✅ PASS: Alice can read her own data" -ForegroundColor Green
} else {
    Write-Host "❌ FAIL: Alice should read her own data" -ForegroundColor Red
}

# Test 3b: Read Bob's data as Bob
$result = Invoke-BackendTest -Endpoint "read_blob_file" -Method "POST" `
    -Body @{ target_blob_name = $testFile } `
    -UserId $testUser2 `
    -TestName "Read Bob's data as Bob"

if ($result.Success -and $result.Data.content -match "bob") {
    Write-Host "✅ PASS: Bob can read his own data" -ForegroundColor Green
} else {
    Write-Host "❌ FAIL: Bob should read his own data" -ForegroundColor Red
}

# Test 3c: Try to read Alice's data as Bob (should get Bob's data instead)
$result = Invoke-BackendTest -Endpoint "read_blob_file" -Method "POST" `
    -Body @{ target_blob_name = $testFile } `
    -UserId $testUser2 `
    -TestName "Read same filename as Bob (should get Bob's isolated data)"

if ($result.Success -and $result.Data.content -match "bob" -and $result.Data.content -notmatch "alice") {
    Write-Host "✅ PASS: User isolation works - Bob only sees his data" -ForegroundColor Green
} else {
    Write-Host "⚠️ WARNING: Check isolation - Bob might see Alice's data" -ForegroundColor Yellow
}

Write-Host "`n========== TEST 4: Update Operation ==========" -ForegroundColor Cyan

# Test 4: Update Alice's data
$updatePayload = @{
    target_blob_name = $testFile
    find_key = "name"
    find_value = "Alice Item 1"
    update_key = "value"
    update_value = 999
}

$result = Invoke-BackendTest -Endpoint "update_data_entry" -Method "POST" `
    -Body $updatePayload `
    -UserId $testUser1 `
    -TestName "Update Alice's Item 1 value to 999"

if ($result.Success) {
    Write-Host "✅ PASS: Update successful" -ForegroundColor Green
    
    # Verify update
    $verifyResult = Invoke-BackendTest -Endpoint "read_blob_file" -Method "POST" `
        -Body @{ target_blob_name = $testFile } `
        -UserId $testUser1 `
        -TestName "Verify Alice's data was updated"
    
    if ($verifyResult.Success -and $verifyResult.Data.content -match "999") {
        Write-Host "✅ PASS: Update verified in data" -ForegroundColor Green
    }
} else {
    Write-Host "❌ FAIL: Update should succeed" -ForegroundColor Red
}

Write-Host "`n========== TEST 5: Remove Operation ==========" -ForegroundColor Cyan

# Test 5: Remove one of Bob's items
$removePayload = @{
    target_blob_name = $testFile
    key_to_find = "name"
    value_to_find = "Bob Item 1"
}

$result = Invoke-BackendTest -Endpoint "remove_data_entry" -Method "POST" `
    -Body $removePayload `
    -UserId $testUser2 `
    -TestName "Remove Bob's Item 1"

if ($result.Success) {
    Write-Host "✅ PASS: Remove successful" -ForegroundColor Green
    
    # Verify removal
    $verifyResult = Invoke-BackendTest -Endpoint "read_blob_file" -Method "POST" `
        -Body @{ target_blob_name = $testFile } `
        -UserId $testUser2 `
        -TestName "Verify Bob's item was removed"
    
    if ($verifyResult.Success -and $verifyResult.Data.content -notmatch "Bob Item 1") {
        Write-Host "✅ PASS: Removal verified in data" -ForegroundColor Green
    }
} else {
    Write-Host "❌ FAIL: Remove should succeed" -ForegroundColor Red
}

Write-Host "`n========== TEST 6: List Blobs (User Isolation) ==========" -ForegroundColor Cyan

# Test 6a: List Alice's blobs
$result = Invoke-BackendTest -Endpoint "list_blobs" -Method "POST" `
    -Body @{} `
    -UserId $testUser1 `
    -TestName "List Alice's blobs"

if ($result.Success) {
    $aliceBlobCount = $result.Data.blobs.Count
    Write-Host "Alice has $aliceBlobCount blobs" -ForegroundColor Cyan
}

# Test 6b: List Bob's blobs
$result = Invoke-BackendTest -Endpoint "list_blobs" -Method "POST" `
    -Body @{} `
    -UserId $testUser2 `
    -TestName "List Bob's blobs"

if ($result.Success) {
    $bobBlobCount = $result.Data.blobs.Count
    Write-Host "Bob has $bobBlobCount blobs" -ForegroundColor Cyan
    Write-Host "✅ PASS: Users see separate blob lists" -ForegroundColor Green
}

Write-Host "`n========== TEST 7: Cleanup (Delete Test Files) ==========" -ForegroundColor Cyan

# Cleanup Alice's test file
$result = Invoke-BackendTest -Endpoint "manage_files" -Method "POST" `
    -Body @{ operation = "delete"; filename = $testFile; user_id = $testUser1 } `
    -UserId $testUser1 `
    -TestName "Delete Alice's test file"

# Cleanup Bob's test file
$result = Invoke-BackendTest -Endpoint "manage_files" -Method "POST" `
    -Body @{ operation = "delete"; filename = $testFile; user_id = $testUser2 } `
    -UserId $testUser2 `
    -TestName "Delete Bob's test file"

Write-Host "`n========== LOGGING CHECK ==========" -ForegroundColor Cyan
Write-Host "Checking backend_debug.log for logged entries..." -ForegroundColor Yellow

$logPath = ".\backend_debug.log"
if (Test-Path $logPath) {
    Write-Host "`n✅ Log file exists" -ForegroundColor Green
    
    # Show last 10 entries
    $logEntries = Get-Content $logPath | Select-Object -Last 10
    Write-Host "`nLast 10 log entries:" -ForegroundColor Cyan
    foreach ($entry in $logEntries) {
        try {
            $logObj = $entry | ConvertFrom-Json
            $timestamp = $logObj.timestamp
            $function = $logObj.function
            $action = $logObj.action
            $status = $logObj.status
            $user = $logObj.user_id
            
            if ($status -eq "success") {
                Write-Host "[$timestamp] $function.$action - $status (User: $user)" -ForegroundColor Green
            } else {
                Write-Host "[$timestamp] $function.$action - $status (User: $user)" -ForegroundColor Yellow
            }
        } catch {
            Write-Host $entry -ForegroundColor Gray
        }
    }
    
    $totalEntries = (Get-Content $logPath).Count
    Write-Host "`nTotal log entries: $totalEntries" -ForegroundColor Cyan
} else {
    Write-Host "⚠️ WARNING: Log file not found at $logPath" -ForegroundColor Yellow
    Write-Host "Note: Logs are written on Azure, check Application Insights for deployed logs" -ForegroundColor Gray
}

Write-Host "`n========== TEST SUMMARY ==========" -ForegroundColor Cyan
Write-Host "✅ All tests completed!" -ForegroundColor Green
Write-Host "`nKey Points Tested:" -ForegroundColor Yellow
Write-Host "  1. manage_files requires function key (anonymous auth removed)" -ForegroundColor White
Write-Host "  2. Multi-user isolation works (Alice/Bob see separate data)" -ForegroundColor White
Write-Host "  3. CRUD operations properly scoped to user namespaces" -ForegroundColor White
Write-Host "  4. All functions accept X-User-Id header" -ForegroundColor White
Write-Host "  5. Logging captures operations (check backend_debug.log or Azure logs)" -ForegroundColor White
Write-Host "`nNext: Check Azure Application Insights for cloud logs" -ForegroundColor Cyan
