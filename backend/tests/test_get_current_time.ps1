# Test get_current_time via tool_call_handler
. "$PSScriptRoot/test_env.ps1"

$Url = "$BaseUrl/tool_call_handler?code=$FunctionKey"
$Body = @{ tool_name = "get_current_time"; tool_arguments = @{}; user_id = "test_user_123" } | ConvertTo-Json -Depth 5
$Headers = $DefaultHeaders

Write-Host "Testing get_current_time via tool_call_handler..."
$StartTime = Get-Date
try {
    $Response = Invoke-RestMethod -Uri $Url -Method POST -Body $Body -ContentType "application/json" -Headers $Headers -ErrorAction Stop
    $Duration = (Get-Date) - $StartTime
    Write-Host "✅ PASS get_current_time - $($Duration.TotalMilliseconds)ms" -ForegroundColor Green
    Write-Host "  Response: $(($Response | ConvertTo-Json -Depth 1) -replace "`n", " ")" -ForegroundColor Gray
} catch {
    $Duration = (Get-Date) - $StartTime
    Write-Host "❌ FAIL get_current_time - $($Duration.TotalMilliseconds)ms" -ForegroundColor Red
    Write-Host $_.Exception.Message
}
