# Test get_current_time via tool_call_handler (agent path)
. "$PSScriptRoot/test_env.ps1"

$Url = "$BaseUrl/tool_call_handler?code=$FunctionKey"
$Body = @{ message = "What time is it?"; user_id = "test_user_123" } | ConvertTo-Json -Depth 5
$Headers = $DefaultHeaders

Write-Host "Testing get_current_time via tool_call_handler (agent)..."
$StartTime = Get-Date
try {
    $Response = Invoke-RestMethod -Uri $Url -Method POST -Body $Body -ContentType "application/json" -Headers $Headers -ErrorAction Stop
    $Duration = (Get-Date) - $StartTime
    Write-Host "✅ PASS get_current_time (agent) - $($Duration.TotalMilliseconds)ms" -ForegroundColor Green
    Write-Host "  Response: $(($Response | ConvertTo-Json -Depth 1) -replace "`n", " ")" -ForegroundColor Gray
} catch {
    $Duration = (Get-Date) - $StartTime
    Write-Host "❌ FAIL get_current_time (agent) - $($Duration.TotalMilliseconds)ms" -ForegroundColor Red
    Write-Host $_.Exception.Message
}
