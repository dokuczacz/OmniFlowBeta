#!/usr/bin/env pwsh
# Test read_blob_file with user isolation
# Simple, no special characters

Write-Host "=== read_blob_file User Isolation Test ===" -ForegroundColor Cyan
Write-Host ""

# Activate venv
& .\.venv\Scripts\Activate.ps1

# [1] Create Alice's file
Write-Host "[1/5] Creating tasks.json for Alice..." -ForegroundColor Yellow
$aliceContent = @(
    @{ id = "A1"; status = "open"; title = "Alice Task 1" },
    @{ id = "A2"; status = "done"; title = "Alice Task 2" }
)
$aliceUploadBody = @{
    target_blob_name = "tasks.json"
    file_content = $aliceContent
    user_id = "alice_test_123"
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:7071/api/upload_data_or_file" `
    -Method POST -Body $aliceUploadBody -ContentType "application/json" | Out-Null
Write-Host "Done - File created at users/alice_test_123/tasks.json" -ForegroundColor Green

# [2] Create Bob's file
Write-Host "[2/5] Creating tasks.json for Bob..." -ForegroundColor Yellow
$bobContent = @(
    @{ id = "B1"; status = "open"; title = "Bob Task 1" },
    @{ id = "B2"; status = "pending"; title = "Bob Task 2" }
)
$bobUploadBody = @{
    target_blob_name = "tasks.json"
    file_content = $bobContent
    user_id = "bob_test_456"
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:7071/api/upload_data_or_file" `
    -Method POST -Body $bobUploadBody -ContentType "application/json" | Out-Null
Write-Host "Done - File created at users/bob_test_456/tasks.json" -ForegroundColor Green

# [3] Alice reads her file
Write-Host ""
Write-Host "[3/5] Alice reads her own file (header X-User-Id: alice_test_123)..." -ForegroundColor Yellow
$aliceRead = Invoke-RestMethod -Uri "http://localhost:7071/api/read_blob_file?file_name=tasks.json" `
    -Method GET -Headers @{ "X-User-Id" = "alice_test_123" }

Write-Host "Result:" -ForegroundColor Green
Write-Host "  Status: $($aliceRead.status)" -ForegroundColor White
Write-Host "  User ID: $($aliceRead.user_id)" -ForegroundColor White
Write-Host "  Entries: $($aliceRead.data.Count)" -ForegroundColor White
$aliceRead.data | ForEach-Object { Write-Host "    - $($_.title)" -ForegroundColor DarkGray }

# [4] Bob reads his file
Write-Host ""
Write-Host "[4/5] Bob reads his own file (header X-User-Id: bob_test_456)..." -ForegroundColor Yellow
$bobRead = Invoke-RestMethod -Uri "http://localhost:7071/api/read_blob_file?file_name=tasks.json" `
    -Method GET -Headers @{ "X-User-Id" = "bob_test_456" }

Write-Host "Result:" -ForegroundColor Green
Write-Host "  Status: $($bobRead.status)" -ForegroundColor White
Write-Host "  User ID: $($bobRead.user_id)" -ForegroundColor White
Write-Host "  Entries: $($bobRead.data.Count)" -ForegroundColor White
$bobRead.data | ForEach-Object { Write-Host "    - $($_.title)" -ForegroundColor DarkGray }

# [5] Verify isolation
Write-Host ""
Write-Host "[5/5] VERIFICATION:" -ForegroundColor Yellow

$aliceCorrect = ($aliceRead.status -eq "success") -and `
                ($aliceRead.user_id -eq "alice_test_123") -and `
                ($aliceRead.data[0].id -eq "A1")

$bobCorrect = ($bobRead.status -eq "success") -and `
              ($bobRead.user_id -eq "bob_test_456") -and `
              ($bobRead.data[0].id -eq "B1")

$isolated = ($aliceRead.data[0].id -ne $bobRead.data[0].id)

Write-Host ""
if ($aliceCorrect -and $bobCorrect -and $isolated) {
    Write-Host "PASS: User isolation working correctly!" -ForegroundColor Green
    Write-Host "  - Alice sees only her data (A1, A2)" -ForegroundColor Green
    Write-Host "  - Bob sees only his data (B1, B2)" -ForegroundColor Green
    Write-Host "  - User IDs correctly returned" -ForegroundColor Green
} else {
    Write-Host "FAIL: Isolation not working!" -ForegroundColor Red
    if (-not $aliceCorrect) { Write-Host "  - Alice read failed" -ForegroundColor Red }
    if (-not $bobCorrect) { Write-Host "  - Bob read failed" -ForegroundColor Red }
    if (-not $isolated) { Write-Host "  - Data not isolated" -ForegroundColor Red }
}

Write-Host ""
Write-Host "=== Test Complete ===" -ForegroundColor Cyan
