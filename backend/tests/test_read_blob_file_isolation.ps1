#!/usr/bin/env pwsh
<#
.SYNOPSIS
Test read_blob_file with user isolation
.DESCRIPTION
Tests that alice and bob can only read their own data, not each other's.
#>

# Activate venv
& .\.venv\Scripts\Activate.ps1

Write-Host "=== read_blob_file User Isolation Test ===" -ForegroundColor Cyan
Write-Host ""

# Prepare test data for Alice
Write-Host "[1/5] Creating tasks.json for Alice..." -ForegroundColor Yellow
$aliceFileContent = @(
    @{ id = "A1"; status = "open"; title = "Alice's Task 1" },
    @{ id = "A2"; status = "done"; title = "Alice's Task 2" }
)
$aliceBody = @{
    target_blob_name = "tasks.json"
    file_content = $aliceFileContent
    user_id = "alice_test_123"
} | ConvertTo-Json -Depth 5

$aliceUpload = Invoke-RestMethod -Uri "http://localhost:7071/api/upload_data_or_file" -Method POST -Body $aliceBody -ContentType "application/json" 2>&1
Write-Host "✓ Alice upload: $($aliceUpload.message)" -ForegroundColor Green

# Prepare test data for Bob
Write-Host "[2/5] Creating tasks.json for Bob..." -ForegroundColor Yellow
$bobFileContent = @(
    @{ id = "B1"; status = "open"; title = "Bob's Task 1" },
    @{ id = "B2"; status = "pending"; title = "Bob's Task 2" }
)
$bobBody = @{
    target_blob_name = "tasks.json"
    file_content = $bobFileContent
    user_id = "bob_test_456"
} | ConvertTo-Json -Depth 5

$bobUpload = Invoke-RestMethod -Uri "http://localhost:7071/api/upload_data_or_file" -Method POST -Body $bobBody -ContentType "application/json" 2>&1
Write-Host "✓ Bob upload: $($bobUpload.message)" -ForegroundColor Green

Write-Host ""
Write-Host "[3/5] Alice reads her own data (via header X-User-Id)..." -ForegroundColor Yellow
$aliceRead = Invoke-WebRequest -Uri "http://localhost:7071/api/read_blob_file?file_name=tasks.json" `
    -Method GET `
    -Headers @{ "X-User-Id" = "alice_test_123" } `
    -ContentType "application/json" `
    -UseBasicParsing 2>&1 | ConvertFrom-Json

Write-Host "✓ Alice read: " -ForegroundColor Green -NoNewline
Write-Host "$($aliceRead.data.Count) entries found" -ForegroundColor White
Write-Host "  Status: $($aliceRead.status)" -ForegroundColor White
Write-Host "  User ID returned: $($aliceRead.user_id)" -ForegroundColor White
$aliceRead.data | ForEach-Object { Write-Host "    - $($_.title)" -ForegroundColor DarkGray }

Write-Host ""
Write-Host "[4/5] Bob reads his own data (via header X-User-Id)..." -ForegroundColor Yellow
$bobRead = Invoke-WebRequest -Uri "http://localhost:7071/api/read_blob_file?file_name=tasks.json" `
    -Method GET `
    -Headers @{ "X-User-Id" = "bob_test_456" } `
    -ContentType "application/json" `
    -UseBasicParsing 2>&1 | ConvertFrom-Json

Write-Host "✓ Bob read: " -ForegroundColor Green -NoNewline
Write-Host "$($bobRead.data.Count) entries found" -ForegroundColor White
Write-Host "  Status: $($bobRead.status)" -ForegroundColor White
Write-Host "  User ID returned: $($bobRead.user_id)" -ForegroundColor White
$bobRead.data | ForEach-Object { Write-Host "    - $($_.title)" -ForegroundColor DarkGray }

Write-Host ""
Write-Host "[5/5] ISOLATION VERIFICATION..." -ForegroundColor Yellow

# Verify data isolation
$aliceDataMatch = ($aliceRead.data[0].title -like "Alice*") -and ($bobRead.data[0].title -like "Bob*")
$userIdCorrect = ($aliceRead.user_id -eq "alice_test_123") -and ($bobRead.user_id -eq "bob_test_456")
$differentData = ($aliceRead.data.Count -eq 2) -and ($bobRead.data.Count -eq 2) -and `
                 ($aliceRead.data[0].id -ne $bobRead.data[0].id)

if ($aliceDataMatch -and $userIdCorrect -and $differentData) {
    Write-Host "✅ PASS: User isolation working correctly!" -ForegroundColor Green
    Write-Host "  - Alice sees only her data (A1, A2)" -ForegroundColor Green
    Write-Host "  - Bob sees only his data (B1, B2)" -ForegroundColor Green
    Write-Host "  - User IDs correctly returned in responses" -ForegroundColor Green
} else {
    Write-Host "❌ FAIL: Isolation not working!" -ForegroundColor Red
    if (-not $aliceDataMatch) { Write-Host "  - Data content mismatch" -ForegroundColor Red }
    if (-not $userIdCorrect) { Write-Host "  - User IDs not returned correctly" -ForegroundColor Red }
    if (-not $differentData) { Write-Host "  - Data not isolated between users" -ForegroundColor Red }
}

Write-Host ""
Write-Host "=== Test Complete ===" -ForegroundColor Cyan
