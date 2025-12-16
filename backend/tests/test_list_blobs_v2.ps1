# Test script for list_blobs with user isolation
# Validates that users can only list their own blobs

Write-Host "=== Testing list_blobs with user isolation ===" -ForegroundColor Cyan

# Test users
$aliceUserId = "alice_test_123"
$bobUserId = "bob_test_456"

# Step 1: Setup - Create test files for Alice
Write-Host "`n[1/5] Creating test files for Alice..." -ForegroundColor Yellow

$aliceFile1 = @{
    target_blob_name = "tasks.json"
    file_content = @(@{id="A1"; task="Alice task 1"}, @{id="A2"; task="Alice task 2"})
} | ConvertTo-Json -Depth 5

$aliceFile2 = @{
    target_blob_name = "notes.json"
    file_content = @(@{id="A3"; note="Alice note"})
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
Write-Host "`n[2/5] Creating test files for Bob..." -ForegroundColor Yellow

$bobFile1 = @{
    target_blob_name = "tasks.json"
    file_content = @(@{id="B1"; task="Bob task 1"})
} | ConvertTo-Json -Depth 5

$bobFile2 = @{
    target_blob_name = "projects.json"
    file_content = @(@{id="B2"; project="Bob project"})
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

# Step 3: List Alice's blobs
Write-Host "`n[3/5] Listing Alice's blobs..." -ForegroundColor Yellow

$aliceList = Invoke-RestMethod -Uri "http://localhost:7071/api/list_blobs" `
    -Method Get `
    -Headers @{"x-user-id"=$aliceUserId}

Write-Host "Alice's response: $($aliceList | ConvertTo-Json -Compress)" -ForegroundColor Cyan

# Step 4: List Bob's blobs
Write-Host "`n[4/5] Listing Bob's blobs..." -ForegroundColor Yellow

$bobList = Invoke-RestMethod -Uri "http://localhost:7071/api/list_blobs" `
    -Method Get `
    -Headers @{"x-user-id"=$bobUserId}

Write-Host "Bob's response: $($bobList | ConvertTo-Json -Compress)" -ForegroundColor Cyan

# Step 5: Validate isolation
Write-Host "`n[5/5] Validating user isolation..." -ForegroundColor Yellow

$errors = @()

# Check Alice has correct user_id
if ($aliceList.user_id -ne $aliceUserId) {
    $errors += "Alice's user_id is incorrect: $($aliceList.user_id)"
}

# Check Bob has correct user_id
if ($bobList.user_id -ne $bobUserId) {
    $errors += "Bob's user_id is incorrect: $($bobList.user_id)"
}

# Check Alice sees 2 blobs
if ($aliceList.count -ne 2) {
    $errors += "Alice should see 2 blobs, got $($aliceList.count)"
}

# Check Bob sees 2 blobs
if ($bobList.count -ne 2) {
    $errors += "Bob should see 2 blobs, got $($bobList.count)"
}

# Check Alice sees her files (tasks.json, notes.json)
$aliceHasTasks = $aliceList.blobs -contains "tasks.json"
$aliceHasNotes = $aliceList.blobs -contains "notes.json"
if (-not $aliceHasTasks -or -not $aliceHasNotes) {
    $errors += "Alice should see tasks.json and notes.json"
}

# Check Bob sees his files (tasks.json, projects.json)
$bobHasTasks = $bobList.blobs -contains "tasks.json"
$bobHasProjects = $bobList.blobs -contains "projects.json"
if (-not $bobHasTasks -or -not $bobHasProjects) {
    $errors += "Bob should see tasks.json and projects.json"
}

# Check Alice doesn't see Bob's projects.json
$aliceSeesProjects = $aliceList.blobs -contains "projects.json"
if ($aliceSeesProjects) {
    $errors += "Alice should NOT see projects.json (Bob's file)"
}

# Check Bob doesn't see Alice's notes.json
$bobSeesNotes = $bobList.blobs -contains "notes.json"
if ($bobSeesNotes) {
    $errors += "Bob should NOT see notes.json (Alice's file)"
}

# Final result
if ($errors.Count -eq 0) {
    Write-Host "`n✅ PASS: list_blobs with isolation working!" -ForegroundColor Green
    Write-Host "  - Alice sees 2 files: tasks.json, notes.json" -ForegroundColor Green
    Write-Host "  - Bob sees 2 files: tasks.json, projects.json" -ForegroundColor Green
    Write-Host "  - No cross-user visibility" -ForegroundColor Green
} else {
    Write-Host "`n❌ FAIL: Issues detected:" -ForegroundColor Red
    $errors | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
}
