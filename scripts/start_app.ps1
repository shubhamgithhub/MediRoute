<#
Start MediRoute locally: stops any MediRoute backend / frontend already running, starts both in
their own windows, waits until the backend answers, then opens the patient page.

First go to the MediRoute folder (the one that contains pyproject.toml), e.g.:

    cd "C:\Users\<you>\Projects\MediRoute"

then:

    powershell -ExecutionPolicy Bypass -File scripts\start_app.ps1
    powershell -ExecutionPolicy Bypass -File scripts\start_app.ps1 -Stop          # only stop
    powershell -ExecutionPolicy Bypass -File scripts\start_app.ps1 -NoBrowser     # do not open the browser
    powershell -ExecutionPolicy Bypass -File scripts\start_app.ps1 -Model "openai/gpt-6-luna"

Only MediRoute's own processes are stopped (found by their command line); another program on
port 8000 or 5500 is reported, never stopped. Close a server window (or press Ctrl+C in it) to stop it.
Run scripts\setup_windows.ps1 once first.
#>
param(
    [switch]$Stop,
    [switch]$NoBrowser,
    [string]$Model = ""
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
$BackendPort = 8000
$FrontendPort = 5500
$DefaultModel = "openai/gpt-6-luna"   # the model used in the benchmarks and the report

function Get-MediRouteProcesses {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and $_.CommandLine -match "uvicorn\s+mediroute\.backend\.main|serve_frontend\.py"
    }
}

function Stop-MediRoute {
    $procs = @(Get-MediRouteProcesses)
    if (-not $procs.Count) { Write-Host "  nothing running" ; return }
    foreach ($p in $procs) {
        $what = if ($p.CommandLine -match "serve_frontend") { "frontend" } else { "backend" }
        Write-Host ("  stopping {0} (process {1})" -f $what, $p.ProcessId)
        Stop-Process -Id $p.ProcessId -Force -Confirm:$false -ErrorAction SilentlyContinue
    }
    # wait until the ports are released
    for ($i = 0; $i -lt 20; $i++) {
        $busy = Get-NetTCPConnection -LocalPort $BackendPort, $FrontendPort -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $procs.ProcessId -contains $_.OwningProcess }
        if (-not $busy) { break }
        Start-Sleep -Milliseconds 500
    }
}

function Test-PortFree($Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) { return $true }
    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    $name = if ($proc) { $proc.ProcessName } else { "process $($conn.OwningProcess)" }
    Write-Host "  port $Port is used by $name (not MediRoute). Close it, then run this again." -ForegroundColor Red
    return $false
}

Write-Host "== Stopping MediRoute if it is running" -ForegroundColor Cyan
Stop-MediRoute
if ($Stop) { Write-Host "Stopped." -ForegroundColor Green; exit 0 }

if (-not (Test-Path $VenvPy)) {
    Write-Host ".venv not found. Run setup first: powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1" -ForegroundColor Red
    exit 1
}
if (-not ((Test-PortFree $BackendPort) -and (Test-PortFree $FrontendPort))) { exit 1 }

# ---------------------------------------------------------------- settings for the backend window
if (-not $Model) { $Model = $env:MEDIROUTE_OPENROUTER_MODEL }
if (-not $Model) { $Model = [Environment]::GetEnvironmentVariable("MEDIROUTE_OPENROUTER_MODEL", "User") }
if (-not $Model) { $Model = $DefaultModel }
$hasKey = [bool]($env:OPENROUTER_API_KEY -or [Environment]::GetEnvironmentVariable("OPENROUTER_API_KEY", "User"))
if ($hasKey) { Write-Host "LLM: OpenRouter, model $Model" }
else { Write-Host "LLM: no OPENROUTER_API_KEY; the app runs on the lookup only (see README section 4)." -ForegroundColor Yellow }

$freeGb = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
if ($freeGb -lt 2.5) { Write-Host "Only $freeGb GB RAM free; start-up may be slow. Close Teams / browser tabs if it times out." -ForegroundColor Yellow }

# ---------------------------------------------------------------- start both windows
# single quotes inside the command keep paths with spaces intact
$q = { param($s) "'" + ($s -replace "'", "''") + "'" }
$backendCmd = "`$host.UI.RawUI.WindowTitle = 'MediRoute backend :$BackendPort'; " +
    "Set-Location $(& $q $Root); `$env:MEDIROUTE_OPENROUTER_MODEL = $(& $q $Model); " +
    "& $(& $q $VenvPy) -m uvicorn mediroute.backend.main:app --host 127.0.0.1 --port $BackendPort"
$frontendCmd = "`$host.UI.RawUI.WindowTitle = 'MediRoute frontend :$FrontendPort'; " +
    "Set-Location $(& $q $Root); & $(& $q $VenvPy) scripts\serve_frontend.py --port $FrontendPort"

Write-Host "== Starting backend (port $BackendPort) and frontend (port $FrontendPort) in new windows" -ForegroundColor Cyan
Start-Process powershell -ArgumentList @("-NoExit", "-NoProfile", "-Command", $backendCmd) -WorkingDirectory $Root
Start-Process powershell -ArgumentList @("-NoExit", "-NoProfile", "-Command", $frontendCmd) -WorkingDirectory $Root

# ---------------------------------------------------------------- wait for the backend
Write-Host "Waiting for the backend (about 30 s; up to 3 min on the very first start) " -NoNewline
$healthy = $false
for ($i = 0; $i -lt 90; $i++) {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/health" -TimeoutSec 2
        if ($r.status) { $healthy = $true; break }
    } catch { }
    Write-Host "." -NoNewline
    Start-Sleep -Seconds 2
}
Write-Host ""
if (-not $healthy) {
    Write-Host "The backend did not answer within 3 minutes. Look at the 'MediRoute backend' window for the error." -ForegroundColor Red
    exit 1
}
Write-Host "Backend: $($r.status)" -ForegroundColor Green
Write-Host "The first search can take a little longer while the LLM warms up."
Write-Host ""
Write-Host "Patient page: http://127.0.0.1:$FrontendPort/index.html"
Write-Host "Admin page:   http://127.0.0.1:$FrontendPort/admin.html"
Write-Host "API docs:     http://127.0.0.1:$BackendPort/docs"
Write-Host "Stop:         powershell -ExecutionPolicy Bypass -File scripts\start_app.ps1 -Stop   (or close both windows)"
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$FrontendPort/index.html" }
exit 0
