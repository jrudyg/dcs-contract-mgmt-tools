# install-anonymizer.ps1
# One-time setup for the DCS Contract Anonymizer (routes live inside server.py).
#
# What it does:
#   1. Detect Python (prompt with guidance if missing)
#   2. Install pip dependencies for the anonymization pipeline
#   3. Download the spaCy en_core_web_lg model
#   4. Verify required files are present (anonymize.py, mapping.json, COUNTERPARTIES.md)
#   5. Ensure the DCS-Contract-Scanner task exists (skip if already registered)
#   6. Restart the task so the new /anonymize routes load, then verify localhost:5000
#
# Assumes an elevated (Administrator) PowerShell session for the Task Scheduler step.
# Re-runnable: every step is idempotent (skip-if-present).

$ErrorActionPreference = "Stop"

$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$anonDir  = Join-Path $toolsDir "anonymization"
$kbDir    = Join-Path $toolsDir "kb"
$server   = Join-Path $toolsDir "server.py"
$taskName = "DCS-Contract-Scanner"

function Step($n, $msg) { Write-Host ""; Write-Host "[$n] $msg" -ForegroundColor Cyan }
function OK($msg)       { Write-Host "    OK  $msg" -ForegroundColor Green }
function Warn($msg)     { Write-Host "    !   $msg" -ForegroundColor Yellow }
function Fail($msg)     { Write-Host "    X   $msg" -ForegroundColor Red }

# ── 1. Detect Python ────────────────────────────────────────────────────────
Step 1 "Detecting Python"
$python = $null
try { $python = (Get-Command python -ErrorAction Stop).Source } catch {}
if (-not $python) {
    Fail "Python not found on PATH."
    Write-Host ""
    Write-Host "    Install Python 3.11+ from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "    During install, CHECK 'Add python.exe to PATH', then re-run this script." -ForegroundColor Yellow
    exit 1
}
$pyver = & $python --version 2>&1
OK "$pyver at $python"

# ── 2. Pip dependencies ──────────────────────────────────────────────────────
Step 2 "Installing pip dependencies"
$deps = @(
    "pdfplumber",
    "python-docx",
    "presidio-analyzer",
    "presidio-anonymizer",
    "spacy"
)
Write-Host "    Upgrading pip..."
& $python -m pip install --upgrade pip --quiet
foreach ($d in $deps) {
    Write-Host "    pip install $d ..."
    & $python -m pip install $d --quiet
    if ($LASTEXITCODE -ne 0) { Fail "pip install $d failed."; exit 1 }
}
OK "All pip dependencies installed."

# ── 3. spaCy model ────────────────────────────────────────────────────────────
Step 3 "Ensuring spaCy en_core_web_lg model"
$modelPresent = $false
& $python -c "import spacy; spacy.load('en_core_web_lg')" 2>$null
if ($LASTEXITCODE -eq 0) { $modelPresent = $true }
if ($modelPresent) {
    OK "en_core_web_lg already installed."
} else {
    Write-Host "    Downloading en_core_web_lg (~560 MB)..."
    & $python -m spacy download en_core_web_lg
    if ($LASTEXITCODE -ne 0) { Fail "spaCy model download failed."; exit 1 }
    OK "en_core_web_lg downloaded."
}

# ── 4. Required files ──────────────────────────────────────────────────────────
Step 4 "Checking required files"
$required = @(
    @{ Path = (Join-Path $anonDir "anonymize.py");   Label = "anonymization\anonymize.py" },
    @{ Path = (Join-Path $anonDir "mapping.json");    Label = "anonymization\mapping.json" },
    @{ Path = (Join-Path $kbDir   "COUNTERPARTIES.md"); Label = "kb\COUNTERPARTIES.md" },
    @{ Path = $server;                                Label = "server.py" }
)
$missing = @()
foreach ($r in $required) {
    if (Test-Path $r.Path) { OK $r.Label }
    else { Fail "MISSING: $($r.Label)"; $missing += $r.Label }
}
if ($missing.Count -gt 0) {
    Write-Host ""
    Fail "Cannot continue — missing files above. Restore them from the repo, then re-run."
    exit 1
}

# ── 5. Ensure scheduled task (skip if present) ────────────────────────────────
Step 5 "Ensuring scheduled task '$taskName'"
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    OK "Task already registered — skipping registration."
} else {
    Write-Host "    Task not found — registering..."
    $pythonw = Join-Path (Split-Path $python) "pythonw.exe"
    $exe     = if (Test-Path $pythonw) { $pythonw } else { $python }
    $action   = New-ScheduledTaskAction -Execute $exe -Argument "`"$server`""
    $trigger  = New-ScheduledTaskTrigger -AtLogon -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew `
        -Hidden `
        -StartWhenAvailable
    try {
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
        OK "Task registered."
    } catch {
        Fail "Task registration failed (need elevated PowerShell?): $_"
        exit 1
    }
}

# ── 6. Restart task to load new routes + verify ───────────────────────────────
Step 6 "Restarting task to load new /anonymize routes"
try {
    Restart-ScheduledTask -TaskName $taskName -ErrorAction Stop
    OK "Task restarted."
} catch {
    Warn "Restart-ScheduledTask failed; trying stop/start..."
    Stop-ScheduledTask  -TaskName $taskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
}

Write-Host "    Waiting for server to come up..."
Start-Sleep -Seconds 4

$up = $false
for ($i = 0; $i -lt 5; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:5000/anonymize" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        if ($resp.StatusCode -eq 200) { $up = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}

Write-Host ""
if ($up) {
    OK "Anonymizer is live at http://localhost:5000/anonymize"
    Write-Host ""
    Write-Host "Setup complete." -ForegroundColor Green
} else {
    Warn "Server not responding at /anonymize yet. It may still be starting."
    Write-Host "    Check http://localhost:5000/anonymize in a moment." -ForegroundColor Yellow
    Write-Host "    If it stays down, run from Tools\:  python server.py   (to see startup errors)" -ForegroundColor Yellow
}
