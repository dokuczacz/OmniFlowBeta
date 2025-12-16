#!/usr/bin/env pwsh
# Test remove_data_entry with user isolation

Write-Host "=== remove_data_entry User Isolation Test ===" -ForegroundColor Cyan
Write-Host ""

& .\.venv\Scripts\Activate.ps1

# [1] Initialize Alice's data
Write-Host "[1/5] Initializing Alice's data (3 entries)..." -ForegroundColor Yellow
$aliceData = @(
    @{ id = "A1"; status = "open"; title = "Alice Task 1" },
    @{ id = "A2"; status = "done"; title = "Alice Task 2" },
    @{ id = "A3"; status = "open"; title = "Alice Task 3" }
)
$aliceInitBody = @{
    target_blob_name = "tasks.json"
    file_content = $aliceData
    user_id = "alice_test_123"
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:7071/api/upload_data_or_file" `
    -Method POST -Body $aliceInitBody -ContentType "application/json" | Out-Null
Write-Host "Done - 3 entries" -ForegroundColor Green

# [2] Initialize Bob's data
Write-Host "[2/5] Initializing Bob's data (3 entries)..." -ForegroundColor Yellow
$bobData = @(
    @{ id = "B1"; status = "open"; title = "Bob Task 1" },
    @{ id = "B2"; status = "open"; title = "Bob Task 2" },
    @{ id = "B3"; status = "done"; title = "Bob Task 3" }
)
$bobInitBody = @{
    target_blob_name = "tasks.json"
    file_content = $bobData
    user_id = "bob_test_456"
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:7071/api/upload_data_or_file" `
    -Method POST -Body $bobInitBody -ContentType "application/json" | Out-Null
Write-Host "Done - 3 entries" -ForegroundColor Green

# [3] Alice removes task A2
Write-Host ""
Write-Host "[3/5] Alice removing task A2..." -ForegroundColor Yellow
$aliceRemoveBody = @{
    target_blob_name = "tasks.json"
    key_to_find = "id"
    value_to_find = "A2"
} | ConvertTo-Json -Depth 5

$aliceRemove = Invoke-RestMethod -Uri "http://localhost:7071/api/remove_data_entry" `
    -Method POST -Body $aliceRemoveBody -ContentType "application/json" `
    -Headers @{ "X-User-Id" = "alice_test_123" }

Write-Host "Result:" -ForegroundColor Green
Write-Host "  Status: $($aliceRemove.status)" -ForegroundColor White
Write-Host "  User ID: $($aliceRemove.user_id)" -ForegroundColor White
Write-Host "  Deleted count: $($aliceRemove.deleted_count)" -ForegroundColor White

# [4] Bob removes task B3
Write-Host ""
Write-Host "[4/5] Bob removing task B3..." -ForegroundColor Yellow
$bobRemoveBody = @{
    target_blob_name = "tasks.json"
    key_to_find = "id"
    value_to_find = "B3"
} | ConvertTo-Json -Depth 5

$bobRemove = Invoke-RestMethod -Uri "http://localhost:7071/api/remove_data_entry" `
    -Method POST -Body $bobRemoveBody -ContentType "application/json" `
    -Headers @{ "X-User-Id" = "bob_test_456" }

Write-Host "Result:" -ForegroundColor Green
Write-Host "  Status: $($bobRemove.status)" -ForegroundColor White
Write-Host "  User ID: $($bobRemove.user_id)" -ForegroundColor White
Write-Host "  Deleted count: $($bobRemove.deleted_count)" -ForegroundColor White

# [5] Verify removals
Write-Host ""
Write-Host "[5/5] Verifying after removal..." -ForegroundColor Yellow

$aliceRead = Invoke-RestMethod -Uri "http://localhost:7071/api/read_blob_file?file_name=tasks.json" `
    -Method GET -Headers @{ "X-User-Id" = "alice_test_123" }

$bobRead = Invoke-RestMethod -Uri "http://localhost:7071/api/read_blob_file?file_name=tasks.json" `
    -Method GET -Headers @{ "X-User-Id" = "bob_test_456" }

Write-Host "Alice's remaining tasks:" -ForegroundColor Green
$aliceRead.data | ForEach-Object { Write-Host "  - ID: $($_.id), Title: $($_.title)" -ForegroundColor DarkGray }

Write-Host "Bob's remaining tasks:" -ForegroundColor Green
$bobRead.data | ForEach-Object { Write-Host "  - ID: $($_.id), Title: $($_.title)" -ForegroundColor DarkGray }

# VERIFICATION
Write-Host ""
Write-Host "VERIFICATION:" -ForegroundColor Yellow

$aliceHasA1 = $aliceRead.data | Where-Object { $_.id -eq "A1" }
$aliceHasA2 = $aliceRead.data | Where-Object { $_.id -eq "A2" }
$alicePass = ($aliceRead.data.Count -eq 2) -and ($aliceHasA1 -ne $null) -and ($aliceHasA2 -eq $null) -and ($aliceRemove.status -eq "success")

$bobHasB1 = $bobRead.data | Where-Object { $_.id -eq "B1" }
$bobHasB3 = $bobRead.data | Where-Object { $_.id -eq "B3" }
$bobPass = ($bobRead.data.Count -eq 2) -and ($bobHasB1 -ne $null) -and ($bobHasB3 -eq $null) -and ($bobRemove.status -eq "success")

$aliceNoB = $aliceRead.data | Where-Object { $_.id -like "B*" }
$bobNoA = $bobRead.data | Where-Object { $_.id -like "A*" }
$isolated = ($aliceNoB -eq $null) -and ($bobNoA -eq $null)

Write-Host ""
if ($alicePass -and $bobPass -and $isolated) {
    Write-Host "PASS: remove_data_entry with isolation working!" -ForegroundColor Green
    Write-Host "  - Alice removed A2 (A1, A3 remain)" -ForegroundColor Green
    Write-Host "  - Bob removed B3 (B1, B2 remain)" -ForegroundColor Green
    Write-Host "  - Data isolated correctly" -ForegroundColor Green
} else {
    Write-Host "FAIL: remove_data_entry failed!" -ForegroundColor Red
    if (-not $alicePass) { Write-Host "  - Alice removal failed" -ForegroundColor Red }
    if (-not $bobPass) { Write-Host "  - Bob removal failed" -ForegroundColor Red }
    if (-not $isolated) { Write-Host "  - Data isolation failed" -ForegroundColor Red }
}

Write-Host ""
Write-Host "=== Test Complete ===" -ForegroundColor Cyan
