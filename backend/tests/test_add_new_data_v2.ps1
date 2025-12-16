#!/usr/bin/env pwsh
# Test add_new_data with user isolation

Write-Host "=== add_new_data User Isolation Test ===" -ForegroundColor Cyan
Write-Host ""

& .\.venv\Scripts\Activate.ps1

# [1] Initialize Alice's file
Write-Host "[1/6] Initializing Alice's tasks.json..." -ForegroundColor Yellow
$aliceInitBody = @{
    target_blob_name = "tasks.json"
    file_content = @( @{ id = "A_init"; status = "done"; title = "Initial Task" } )
    user_id = "alice_test_123"
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:7071/api/upload_data_or_file" `
    -Method POST -Body $aliceInitBody -ContentType "application/json" | Out-Null
Write-Host "Done - 1 initial entry" -ForegroundColor Green

# [2] Initialize Bob's file
Write-Host "[2/6] Initializing Bob's tasks.json..." -ForegroundColor Yellow
$bobInitBody = @{
    target_blob_name = "tasks.json"
    file_content = @( @{ id = "B_init"; status = "done"; title = "Bob Initial" } )
    user_id = "bob_test_456"
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:7071/api/upload_data_or_file" `
    -Method POST -Body $bobInitBody -ContentType "application/json" | Out-Null
Write-Host "Done - 1 initial entry" -ForegroundColor Green

# [3] Alice adds entry
Write-Host ""
Write-Host "[3/6] Alice adding new entry (header X-User-Id: alice_test_123)..." -ForegroundColor Yellow
$aliceAddBody = @{
    target_blob_name = "tasks.json"
    new_entry = @{ id = "A1"; status = "open"; title = "Alice New Task" }
} | ConvertTo-Json -Depth 5

$aliceAddResult = Invoke-RestMethod -Uri "http://localhost:7071/api/add_new_data" `
    -Method POST -Body $aliceAddBody -ContentType "application/json" `
    -Headers @{ "X-User-Id" = "alice_test_123" }

Write-Host "Result:" -ForegroundColor Green
Write-Host "  Status: $($aliceAddResult.status)" -ForegroundColor White
Write-Host "  User ID: $($aliceAddResult.user_id)" -ForegroundColor White
Write-Host "  Entry count: $($aliceAddResult.entry_count)" -ForegroundColor White

# [4] Bob adds entry
Write-Host ""
Write-Host "[4/6] Bob adding new entry (header X-User-Id: bob_test_456)..." -ForegroundColor Yellow
$bobAddBody = @{
    target_blob_name = "tasks.json"
    new_entry = @{ id = "B1"; status = "open"; title = "Bob New Task" }
} | ConvertTo-Json -Depth 5

$bobAddResult = Invoke-RestMethod -Uri "http://localhost:7071/api/add_new_data" `
    -Method POST -Body $bobAddBody -ContentType "application/json" `
    -Headers @{ "X-User-Id" = "bob_test_456" }

Write-Host "Result:" -ForegroundColor Green
Write-Host "  Status: $($bobAddResult.status)" -ForegroundColor White
Write-Host "  User ID: $($bobAddResult.user_id)" -ForegroundColor White
Write-Host "  Entry count: $($bobAddResult.entry_count)" -ForegroundColor White

# [5] Alice reads to verify
Write-Host ""
Write-Host "[5/6] Alice reading her file to verify..." -ForegroundColor Yellow
$aliceReadAfterAdd = Invoke-RestMethod -Uri "http://localhost:7071/api/read_blob_file?file_name=tasks.json" `
    -Method GET -Headers @{ "X-User-Id" = "alice_test_123" }

Write-Host "Result:" -ForegroundColor Green
Write-Host "  Entry count: $($aliceReadAfterAdd.data.Count)" -ForegroundColor White
$aliceReadAfterAdd.data | ForEach-Object { Write-Host "    - ID: $($_.id), Title: $($_.title)" -ForegroundColor DarkGray }

# [6] Bob reads to verify
Write-Host ""
Write-Host "[6/6] Bob reading his file to verify..." -ForegroundColor Yellow
$bobReadAfterAdd = Invoke-RestMethod -Uri "http://localhost:7071/api/read_blob_file?file_name=tasks.json" `
    -Method GET -Headers @{ "X-User-Id" = "bob_test_456" }

Write-Host "Result:" -ForegroundColor Green
Write-Host "  Entry count: $($bobReadAfterAdd.data.Count)" -ForegroundColor White
$bobReadAfterAdd.data | ForEach-Object { Write-Host "    - ID: $($_.id), Title: $($_.title)" -ForegroundColor DarkGray }

# VERIFICATION
Write-Host ""
Write-Host "VERIFICATION:" -ForegroundColor Yellow

$aliceAdd1 = ($aliceAddResult.user_id -eq "alice_test_123") -and `
             ($aliceAddResult.entry_count -eq 2) -and `
             ($aliceReadAfterAdd.data.Count -eq 2) -and `
             ($aliceReadAfterAdd.data[1].id -eq "A1")

$bobAdd1 = ($bobAddResult.user_id -eq "bob_test_456") -and `
           ($bobAddResult.entry_count -eq 2) -and `
           ($bobReadAfterAdd.data.Count -eq 2) -and `
           ($bobReadAfterAdd.data[1].id -eq "B1")

$isolated = ($aliceReadAfterAdd.data.Count -eq 2) -and `
            ($bobReadAfterAdd.data.Count -eq 2) -and `
            ($aliceReadAfterAdd.data[1].id -eq "A1") -and `
            ($bobReadAfterAdd.data[1].id -eq "B1")

Write-Host ""
if ($aliceAdd1 -and $bobAdd1 -and $isolated) {
    Write-Host "PASS: add_new_data with user isolation working!" -ForegroundColor Green
    Write-Host "  - Alice can add entries to her file" -ForegroundColor Green
    Write-Host "  - Bob can add entries to his file" -ForegroundColor Green
    Write-Host "  - Data isolated correctly" -ForegroundColor Green
} else {
    Write-Host "FAIL: add_new_data isolation failed!" -ForegroundColor Red
    if (-not $aliceAdd1) { Write-Host "  - Alice add failed" -ForegroundColor Red }
    if (-not $bobAdd1) { Write-Host "  - Bob add failed" -ForegroundColor Red }
    if (-not $isolated) { Write-Host "  - Data isolation failed" -ForegroundColor Red }
}

Write-Host ""
Write-Host "=== Test Complete ===" -ForegroundColor Cyan
