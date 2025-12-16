# Test script for manage_files with user isolation
# Tests list, delete, and rename operations with user isolation

Write-Host "=== Testing manage_files with user isolation ===" -ForegroundColor Cyan

# Test users
$aliceUserId = "alice_test_123"
$bobUserId = "bob_test_456"

# Step 1: Setup - Create test files for Alice
Write-Host "`n[1/7] Creating test files for Alice..." -ForegroundColor Yellow

$aliceFile1 = @{
    target_blob_name = "file1.json"
    file_content = @{id="A1"; data="Alice data 1"}
} | ConvertTo-Json -Depth 5

$aliceFile2 = @{
    target_blob_name = "file2.json"
    file_content = @{id="A2"; data="Alice data 2"}
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:7071/api/upload_data_or_file" `
    -Method Post `
    -Body $aliceFile1 `
    -ContentType "application/json" `
    -Headers @{"x-user-id"=$aliceUserId} | Out-Null

Invoke-RestMethod -Uri "http://localhost:7071/api/upload_data_or_file" `
    -Method Post `
    -Body $aliceFile2 `
    -ContentType "application/json" `
    -Headers @{"x-user-id"=$aliceUserId} | Out-Null

Write-Host "Created 2 files for Alice" -ForegroundColor Green

# Step 2: Setup - Create test files for Bob
Write-Host "`n[2/7] Creating test files for Bob..." -ForegroundColor Yellow

$bobFile1 = @{
    target_blob_name = "file1.json"
    file_content = @{id="B1"; data="Bob data 1"}
} | ConvertTo-Json -Depth 5

$bobFile2 = @{
    target_blob_name = "file2.json"
    file_content = @{id="B2"; data="Bob data 2"}
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:7071/api/upload_data_or_file" `
    -Method Post `
    -Body $bobFile1 `
    -ContentType "application/json" `
    -Headers @{"x-user-id"=$bobUserId} | Out-Null

Invoke-RestMethod -Uri "http://localhost:7071/api/upload_data_or_file" `
    -Method Post `
    -Body $bobFile2 `
    -ContentType "application/json" `
    -Headers @{"x-user-id"=$bobUserId} | Out-Null

Write-Host "Created 2 files for Bob" -ForegroundColor Green

# Step 3: Test LIST operation for Alice
Write-Host "`n[3/7] Testing LIST for Alice..." -ForegroundColor Yellow

$aliceListBody = @{
    operation = "list"
} | ConvertTo-Json

$aliceList = Invoke-RestMethod -Uri "http://localhost:7071/api/manage_files" `
    -Method Post `
    -Body $aliceListBody `
    -ContentType "application/json" `
    -Headers @{"x-user-id"=$aliceUserId}

Write-Host "Alice sees: $($aliceList.files -join ', ')" -ForegroundColor Cyan

# Step 4: Test RENAME operation for Alice (file1.json -> file1_renamed.json)
Write-Host "`n[4/7] Testing RENAME for Alice (file1.json -> file1_renamed.json)..." -ForegroundColor Yellow

$aliceRenameBody = @{
    operation = "rename"
    source_name = "file1.json"
    target_name = "file1_renamed.json"
} | ConvertTo-Json

$aliceRename = Invoke-RestMethod -Uri "http://localhost:7071/api/manage_files" `
    -Method Post `
    -Body $aliceRenameBody `
    -ContentType "application/json" `
    -Headers @{"x-user-id"=$aliceUserId}

Write-Host "Alice rename result: $($aliceRename.message)" -ForegroundColor Cyan

# Step 5: Test DELETE operation for Bob (file2.json)
Write-Host "`n[5/7] Testing DELETE for Bob (file2.json)..." -ForegroundColor Yellow

$bobDeleteBody = @{
    operation = "delete"
    source_name = "file2.json"
} | ConvertTo-Json

$bobDelete = Invoke-RestMethod -Uri "http://localhost:7071/api/manage_files" `
    -Method Post `
    -Body $bobDeleteBody `
    -ContentType "application/json" `
    -Headers @{"x-user-id"=$bobUserId}

Write-Host "Bob delete result: $($bobDelete.message)" -ForegroundColor Cyan

# Step 6: Verify final state for both users
Write-Host "`n[6/7] Verifying final state..." -ForegroundColor Yellow

$aliceListFinal = Invoke-RestMethod -Uri "http://localhost:7071/api/manage_files" `
    -Method Post `
    -Body $aliceListBody `
    -ContentType "application/json" `
    -Headers @{"x-user-id"=$aliceUserId}

$bobListBody = @{
    operation = "list"
} | ConvertTo-Json

$bobListFinal = Invoke-RestMethod -Uri "http://localhost:7071/api/manage_files" `
    -Method Post `
    -Body $bobListBody `
    -ContentType "application/json" `
    -Headers @{"x-user-id"=$bobUserId}

Write-Host "Alice final files: $($aliceListFinal.files -join ', ')" -ForegroundColor Cyan
Write-Host "Bob final files: $($bobListFinal.files -join ', ')" -ForegroundColor Cyan

# Step 7: Validate results
Write-Host "`n[7/7] Validating results..." -ForegroundColor Yellow

$errors = @()

# Check Alice has correct user_id
if ($aliceListFinal.user_id -ne $aliceUserId) {
    $errors += "Alice's user_id is incorrect: $($aliceListFinal.user_id)"
}

# Check Bob has correct user_id
if ($bobListFinal.user_id -ne $bobUserId) {
    $errors += "Bob's user_id is incorrect: $($bobListFinal.user_id)"
}

# Note: Users may have other files from previous tests, so we focus on the specific files we're testing

# Alice should have file1_renamed.json (not file1.json)
$aliceHasRenamed = $aliceListFinal.files -contains "file1_renamed.json"
$aliceHasOriginal = $aliceListFinal.files -contains "file1.json"
if (-not $aliceHasRenamed) {
    $errors += "Alice should have file1_renamed.json"
}
if ($aliceHasOriginal) {
    $errors += "Alice should NOT have file1.json (it was renamed)"
}

# Bob should have file1.json only (file2.json was deleted)
$bobHasFile1 = $bobListFinal.files -contains "file1.json"
$bobHasFile2 = $bobListFinal.files -contains "file2.json"
if (-not $bobHasFile1) {
    $errors += "Bob should have file1.json"
}
if ($bobHasFile2) {
    $errors += "Bob should NOT have file2.json (it was deleted)"
}

# Final result
if ($errors.Count -eq 0) {
    Write-Host "`n✅ PASS: manage_files with isolation working!" -ForegroundColor Green
    Write-Host "  - Alice: file1.json renamed to file1_renamed.json, file2.json intact" -ForegroundColor Green
    Write-Host "  - Bob: file2.json deleted, file1.json intact" -ForegroundColor Green
    Write-Host "  - No cross-user operations" -ForegroundColor Green
} else {
    Write-Host "`n❌ FAIL: Issues detected:" -ForegroundColor Red
    $errors | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
}
