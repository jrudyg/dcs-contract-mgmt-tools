# Run once to register server.py as a silent auto-start task.
# After this, the scan server starts automatically at Windows login — no terminal window.
# Re-run to update the registration if paths change.

$toolsDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$script    = Join-Path $toolsDir "server.py"
$taskName  = "DCS-Contract-Scanner"

# Prefer pythonw.exe (no console window) over python.exe
$python    = (Get-Command python -ErrorAction Stop).Source
$pythonw   = Join-Path (Split-Path $python) "pythonw.exe"
$exe       = if (Test-Path $pythonw) { $pythonw } else { $python }

Write-Host "Registering task: $taskName"
Write-Host "  Executable : $exe"
Write-Host "  Script     : $script"

$action   = New-ScheduledTaskAction -Execute $exe -Argument "`"$script`""
$trigger  = New-ScheduledTaskTrigger -AtLogon -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -Hidden `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $taskName `
    -Action   $action `
    -Trigger  $trigger `
    -Settings $settings `
    -Force | Out-Null

Write-Host "Registered. Starting now..."
Start-ScheduledTask -TaskName $taskName

Start-Sleep -Seconds 2

# Verify it came up
$resp = $null
try { $resp = Invoke-WebRequest -Uri "http://localhost:5000" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop } catch {}
if ($resp -and $resp.StatusCode -eq 200) {
    Write-Host "Server is up at http://localhost:5000"
} else {
    Write-Host "Server may still be starting. Try http://localhost:5000 in a moment."
}
