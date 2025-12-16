#!/usr/bin/env pwsh
# Test get_filtered_data with user isolation

Write-Host "=== get_filtered_data User Isolation Test ===" -ForegroundColor Cyan
Write-Host ""

& .\.venv\Scripts\Activate.ps1

# [1] Prepare Alice's data with mixed statuses
Write-Host "[1/5] Initializing Alice's data..." -ForegroundColor Yellow
$aliceData = @(
    @{ id = "A1"; status = "open"; title = "Task 1" },
    @{ id = "A2"; status = "done"; title = "Task 2" },
    @{ id = "A3"; status = "open"; title = "Task 3" }
)
$aliceInitBody = @{
    target_blob_name = "tasks.json"
    file_content = $aliceData
    user_id = "alice_test_123"
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:7071/api/upload_data_or_file" `
    -Method POST -Body $aliceInitBody -ContentType "application/json" | Out-Null
Write-Host "Done - 3 entries (2 open, 1 done)" -ForegroundColor Green

# [2] Prepare Bob's data
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
Write-Host "Done - 2 entries (all open)" -ForegroundColor Green

# [3] Alice filters for open tasks
Write-Host ""
Write-Host "[3/5] Alice filtering for open tasks..." -ForegroundColor Yellow
$aliceFilterBody = @{
    target_blob_name = "tasks.json"
    filter_key = "status"
    filter_value = "open"
} | ConvertTo-Json -Depth 5

$aliceFilter = Invoke-RestMethod -Uri "http://localhost:7071/api/get_filtered_data" `
    -Method POST -Body $aliceFilterBody -ContentType "application/json" `
    -Headers @{ "X-User-Id" = "alice_test_123" }

Write-Host "Result:" -ForegroundColor Green
Write-Host "  Total in file: $($aliceFilter.total)" -ForegroundColor White
Write-Host "  Filtered (open): $($aliceFilter.count)" -ForegroundColor White
$aliceFilter.data | ForEach-Object { Write-Host "    - $($_.title)" -ForegroundColor DarkGray }

# [4] Bob filters for open tasks
Write-Host ""
Write-Host "[4/5] Bob filtering for open tasks..." -ForegroundColor Yellow
$bobFilterBody = @{
    target_blob_name = "tasks.json"
    filter_key = "status"
    filter_value = "open"
} | ConvertTo-Json -Depth 5

$bobFilter = Invoke-RestMethod -Uri "http://localhost:7071/api/get_filtered_data" `
    -Method POST -Body $bobFilterBody -ContentType "application/json" `
    -Headers @{ "X-User-Id" = "bob_test_456" }

Write-Host "Result:" -ForegroundColor Green
Write-Host "  Total in file: $($bobFilter.total)" -ForegroundColor White
Write-Host "  Filtered (open): $($bobFilter.count)" -ForegroundColor White
$bobFilter.data | ForEach-Object { Write-Host "    - $($_.title)" -ForegroundColor DarkGray }

# [5] Verify
Write-Host ""
Write-Host "[5/5] VERIFICATION:" -ForegroundColor Yellow

$alicePass = ($aliceFilter.status -eq "success") -and `
             ($aliceFilter.user_id -eq "alice_test_123") -and `
             ($aliceFilter.total -eq 3) -and `
             ($aliceFilter.count -eq 2) -and `
             ($aliceFilter.filter.key -eq "status")

$bobPass = ($bobFilter.status -eq "success") -and `
           ($bobFilter.user_id -eq "bob_test_456") -and `
           ($bobFilter.total -eq 2) -and `
           ($bobFilter.count -eq 2)

$dataIsolation = ($aliceFilter.data[0].id -like "A*") -and `
                 ($bobFilter.data[0].id -like "B*")

Write-Host ""
if ($alicePass -and $bobPass -and $dataIsolation) {
    Write-Host "PASS: get_filtered_data with isolation working!" -ForegroundColor Green
    Write-Host "  - Alice sees only her data (3 total, 2 open)" -ForegroundColor Green
    Write-Host "  - Bob sees only his data (2 total, 2 open)" -ForegroundColor Green
    Write-Host "  - Filtering works correctly per user" -ForegroundColor Green
} else {
    Write-Host "FAIL: get_filtered_data failed!" -ForegroundColor Red
    if (-not $alicePass) { Write-Host "  - Alice filter failed" -ForegroundColor Red }
    if (-not $bobPass) { Write-Host "  - Bob filter failed" -ForegroundColor Red }
    if (-not $dataIsolation) { Write-Host "  - Data isolation failed" -ForegroundColor Red }
}

Write-Host ""
Write-Host "=== Test Complete ===" -ForegroundColor Cyan
