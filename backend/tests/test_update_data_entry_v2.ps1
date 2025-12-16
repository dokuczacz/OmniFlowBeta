#!/usr/bin/env pwsh
# Test update_data_entry with user isolation

Write-Host "=== update_data_entry User Isolation Test ===" -ForegroundColor Cyan
Write-Host ""

& .\.venv\Scripts\Activate.ps1

# [1] Initialize Alice's data
Write-Host "[1/5] Initializing Alice's data..." -ForegroundColor Yellow
$aliceData = @(
    @{ id = "A1"; status = "open"; title = "Alice Task 1" },
    @{ id = "A2"; status = "open"; title = "Alice Task 2" }
)
$aliceInitBody = @{
    target_blob_name = "tasks.json"
    file_content = $aliceData
    user_id = "alice_test_123"
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:7071/api/upload_data_or_file" `
    -Method POST -Body $aliceInitBody -ContentType "application/json" | Out-Null
Write-Host "Done - 2 entries (both open)" -ForegroundColor Green

# [2] Initialize Bob's data
Write-Host "[2/5] Initializing Bob's data..." -ForegroundColor Yellow
$bobData = @(
    @{ id = "B1"; status = "open"; title = "Bob Task 1" },
    @{ id = "B2"; status = "open"; title = "Bob Task 2" }
)
$bobInitBody = @{
    target_blob_name = "tasks.json"
    file_content = $bobData
    user_id = "bob_test_456"
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:7071/api/upload_data_or_file" `
    -Method POST -Body $bobInitBody -ContentType "application/json" | Out-Null
Write-Host "Done - 2 entries (both open)" -ForegroundColor Green

# [3] Alice updates her task A1
Write-Host ""
Write-Host "[3/5] Alice updating task A1 to 'done'..." -ForegroundColor Yellow
$aliceUpdateBody = @{
    target_blob_name = "tasks.json"
    find_key = "id"
    find_value = "A1"
    update_key = "status"
    update_value = "done"
} | ConvertTo-Json -Depth 5

$aliceUpdate = Invoke-RestMethod -Uri "http://localhost:7071/api/update_data_entry" `
    -Method POST -Body $aliceUpdateBody -ContentType "application/json" `
    -Headers @{ "X-User-Id" = "alice_test_123" }

Write-Host "Result:" -ForegroundColor Green
Write-Host "  Status: $($aliceUpdate.status)" -ForegroundColor White
Write-Host "  User ID: $($aliceUpdate.user_id)" -ForegroundColor White
Write-Host "  Updated: $($aliceUpdate.updated_key) = $($aliceUpdate.updated_value)" -ForegroundColor White

# [4] Bob updates his task B1
Write-Host ""
Write-Host "[4/5] Bob updating task B1 to 'in-progress'..." -ForegroundColor Yellow
$bobUpdateBody = @{
    target_blob_name = "tasks.json"
    find_key = "id"
    find_value = "B1"
    update_key = "status"
    update_value = "in-progress"
} | ConvertTo-Json -Depth 5

$bobUpdate = Invoke-RestMethod -Uri "http://localhost:7071/api/update_data_entry" `
    -Method POST -Body $bobUpdateBody -ContentType "application/json" `
    -Headers @{ "X-User-Id" = "bob_test_456" }

Write-Host "Result:" -ForegroundColor Green
Write-Host "  Status: $($bobUpdate.status)" -ForegroundColor White
Write-Host "  User ID: $($bobUpdate.user_id)" -ForegroundColor White
Write-Host "  Updated: $($bobUpdate.updated_key) = $($bobUpdate.updated_value)" -ForegroundColor White

# [5] Verify updates
Write-Host ""
Write-Host "[5/5] Verifying updates..." -ForegroundColor Yellow

$aliceRead = Invoke-RestMethod -Uri "http://localhost:7071/api/read_blob_file?file_name=tasks.json" `
    -Method GET -Headers @{ "X-User-Id" = "alice_test_123" }

$bobRead = Invoke-RestMethod -Uri "http://localhost:7071/api/read_blob_file?file_name=tasks.json" `
    -Method GET -Headers @{ "X-User-Id" = "bob_test_456" }

Write-Host "Alice's data after update:" -ForegroundColor Green
$aliceRead.data | ForEach-Object { Write-Host "  - ID: $($_.id), Status: $($_.status)" -ForegroundColor DarkGray }

Write-Host "Bob's data after update:" -ForegroundColor Green
$bobRead.data | ForEach-Object { Write-Host "  - ID: $($_.id), Status: $($_.status)" -ForegroundColor DarkGray }

# VERIFICATION
Write-Host ""
Write-Host "VERIFICATION:" -ForegroundColor Yellow

$aliceA1Updated = ($aliceRead.data | Where-Object { $_.id -eq "A1" }).status -eq "done"
$aliceA2Unchanged = ($aliceRead.data | Where-Object { $_.id -eq "A2" }).status -eq "open"
$alicePass = $aliceA1Updated -and $aliceA2Unchanged -and ($aliceUpdate.user_id -eq "alice_test_123")

$bobB1Updated = ($bobRead.data | Where-Object { $_.id -eq "B1" }).status -eq "in-progress"
$bobB2Unchanged = ($bobRead.data | Where-Object { $_.id -eq "B2" }).status -eq "open"
$bobPass = $bobB1Updated -and $bobB2Unchanged -and ($bobUpdate.user_id -eq "bob_test_456")

$isolated = ($aliceRead.data.Count -eq 2) -and ($bobRead.data.Count -eq 2) -and `
            (($aliceRead.data | Where-Object { $_.id -like "B*" }).Count -eq 0)

Write-Host ""
if ($alicePass -and $bobPass -and $isolated) {
    Write-Host "PASS: update_data_entry with isolation working!" -ForegroundColor Green
    Write-Host "  - Alice updated A1 to 'done' (A2 unchanged)" -ForegroundColor Green
    Write-Host "  - Bob updated B1 to 'in-progress' (B2 unchanged)" -ForegroundColor Green
    Write-Host "  - Data isolated correctly" -ForegroundColor Green
} else {
    Write-Host "FAIL: update_data_entry failed!" -ForegroundColor Red
    if (-not $alicePass) { Write-Host "  - Alice update failed" -ForegroundColor Red }
    if (-not $bobPass) { Write-Host "  - Bob update failed" -ForegroundColor Red }
    if (-not $isolated) { Write-Host "  - Data isolation failed" -ForegroundColor Red }
}

Write-Host ""
Write-Host "=== Test Complete ===" -ForegroundColor Cyan
