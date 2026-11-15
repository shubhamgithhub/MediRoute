<#
MediRoute one-click setup for Windows (run once per machine, safe to run again).

First go to the folder where you cloned MediRoute (the one that contains pyproject.toml), e.g.:

    cd "C:\Users\<you>\Projects\MediRoute"

then:

    powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
    powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -RunTests     # also run the tests
    powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -Scraping     # also Playwright (data scrapers)
    powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -Rebuild      # delete and recreate .venv

"-ExecutionPolicy Bypass" applies to this run only; Windows settings are not changed.
Nothing is installed outside the repo folder and no admin rights are needed.
The venv does not need to be activated: run Python as .\.venv\Scripts\python.exe.
#>
param(
    [switch]$RunTests,
    [switch]$Scraping,
    [switch]$Rebuild
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
$Results = New-Object System.Collections.ArrayList

function Add-Result($Name, $Status, $Detail) {
    [void]$Results.Add([pscustomobject]@{ Check = $Name; Status = $Status; Detail = $Detail })
    $color = @{ "OK" = "Green"; "WARN" = "Yellow"; "FAIL" = "Red"; "SKIP" = "DarkGray" }[$Status]
    Write-Host ("  [{0}] {1}: {2}" -f $Status, $Name, $Detail) -ForegroundColor $color
}

function Step($Text) { Write-Host ""; Write-Host "== $Text" -ForegroundColor Cyan }

function Show-Summary {
    Write-Host ""
    Write-Host "==================== Summary ====================" -ForegroundColor Cyan
    foreach ($r in $Results) {
        $color = @{ "OK" = "Green"; "WARN" = "Yellow"; "FAIL" = "Red"; "SKIP" = "DarkGray" }[$r.Status]
        Write-Host ("  [{0}] {1}: {2}" -f $r.Status, $r.Check, $r.Detail) -ForegroundColor $color
    }
}

function Stop-WithError($Message) {
    Write-Host ""
    Write-Host "SETUP STOPPED: $Message" -ForegroundColor Red
    Show-Summary
    exit 1
}

# Runs "<exe> <args> -c <code>" and returns its output, or $null if it failed.
function Invoke-Py($Exe, [string[]]$PreArgs, $Code) {
    try {
        $out = & $Exe @PreArgs -c $Code 2>$null
        if ($LASTEXITCODE -eq 0) { return ($out | Out-String).Trim() }
    } catch { }
    return $null
}

$VersionCode = "import sys; print('%d.%d|%s' % (sys.version_info[0], sys.version_info[1], sys.executable))"
$Supported = @("3.10", "3.11", "3.12", "3.13", "3.14")

Write-Host "MediRoute setup  ($Root)" -ForegroundColor Cyan

# ---------------------------------------------------------------- 1. folder
Step "1. Repo folder"
if (-not (Test-Path (Join-Path $Root "pyproject.toml"))) {
    Stop-WithError "pyproject.toml not found. Run this from the MediRoute folder: scripts\setup_windows.ps1"
}
Add-Result "Repo folder" "OK" $Root

# ---------------------------------------------------------------- 2. Python
Step "2. Python (3.12 recommended; 3.10 to 3.14 work)"
$Python = $null
$candidates = @(
    @{ Exe = "py"; Args = @("-3.12") }, @{ Exe = "py"; Args = @("-3.13") }, @{ Exe = "py"; Args = @("-3.11") },
    @{ Exe = "py"; Args = @("-3.14") }, @{ Exe = "py"; Args = @("-3.10") },
    @{ Exe = "python"; Args = @() }, @{ Exe = "python3"; Args = @() }
)
foreach ($c in $candidates) {
    $cmd = Get-Command $c.Exe -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    # the Microsoft Store shortcut lives in WindowsApps and only opens the Store
    if ($cmd.Source -match "WindowsApps") { continue }
    $info = Invoke-Py $c.Exe $c.Args $VersionCode
    if (-not $info) { continue }
    $ver, $exe = $info.Split("|", 2)
    if ($Supported -contains $ver) { $Python = @{ Exe = $c.Exe; Args = $c.Args; Version = $ver; Path = $exe }; break }
}
if (-not $Python) {
    $found = ""
    if (Get-Command py -ErrorAction SilentlyContinue) { $found = (& py -0 2>$null | Out-String).Trim() }
    if ($found) { Write-Host "  Pythons found by 'py -0':`n$found" }
    Stop-WithError ("No Python 3.10-3.14 found. Install Python 3.12 from https://www.python.org/downloads/ " +
        "and tick 'Add python.exe to PATH'. If 'python' opens the Microsoft Store: Settings > Apps > " +
        "Advanced app settings > App execution aliases > turn off both 'python' entries. Then open a new window and run again.")
}
$pyStatus = "OK"
$pyNote = ""
$venvWillBeCreated = $Rebuild -or -not (Test-Path $VenvPy)
if ($Python.Version -ne "3.12" -and $venvWillBeCreated) { $pyStatus = "WARN"; $pyNote = " (works; 3.12 recommended)" }
if (-not $venvWillBeCreated) { $pyNote = " (not used: the existing .venv has its own Python)" }
Add-Result "Python" $pyStatus ("{0} at {1}{2}" -f $Python.Version, $Python.Path, $pyNote)

# ---------------------------------------------------------------- 3. Git
Step "3. Git"
$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) { Add-Result "Git" "OK" ((& git --version) | Out-String).Trim() }
else { Add-Result "Git" "WARN" "not found (only needed to pull updates): https://git-scm.com/download/win" }

# ---------------------------------------------------------------- 4. venv
Step "4. Virtual environment (.venv)"
$VenvDir = Join-Path $Root ".venv"
if ($Rebuild -and (Test-Path $VenvDir)) {
    Write-Host "  -Rebuild: deleting .venv"
    Remove-Item -Recurse -Force $VenvDir -ErrorAction SilentlyContinue
    if (Test-Path $VenvDir) { Stop-WithError ".venv could not be deleted (close VS Code terminals / running servers that use it, then run again)." }
}
if (Test-Path $VenvPy) {
    $venvInfo = Invoke-Py $VenvPy @() $VersionCode
    if (-not $venvInfo) {
        Stop-WithError ".venv exists but its Python does not start. Run again with -Rebuild to recreate it."
    }
    $venvVer = $venvInfo.Split("|")[0]
    if ($Supported -notcontains $venvVer) {
        Stop-WithError ".venv uses Python $venvVer (not 3.10-3.14). Run again with -Rebuild."
    }
    Add-Result "Virtual env" "OK" "existing .venv (Python $venvVer)"
} else {
    Write-Host "  creating .venv with Python $($Python.Version) ..."
    & $Python.Exe @($Python.Args) -m venv $VenvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPy)) { Stop-WithError "could not create .venv (disk space? antivirus?)." }
    Add-Result "Virtual env" "OK" "created .venv (Python $($Python.Version))"
}

# ---------------------------------------------------------------- 5. install
Step "5. Install packages (first time about 5-10 min; torch is large)"
& $VenvPy -m pip install --upgrade pip --disable-pip-version-check -q
$extras = "dev"
if ($Scraping) { $extras = "dev,scraping" }
& $VenvPy -m pip install -e ".[$extras]" --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    Stop-WithError "pip install failed (see the lines above). Check the internet connection and free disk space (about 3 GB), then run again."
}
Add-Result "Packages" "OK" "pip install -e .[$extras]"
if ($Scraping) {
    & $VenvPy -m playwright install chromium
    if ($LASTEXITCODE -eq 0) { Add-Result "Playwright" "OK" "Chromium installed" }
    else { Add-Result "Playwright" "WARN" "Chromium install failed (only needed for the scrapers)" }
}

# ---------------------------------------------------------------- 6. imports
Step "6. Check the main packages load"
$failed = @()
foreach ($m in @("mediroute", "fastapi", "uvicorn", "numpy", "pandas", "faiss", "torch", "sentence_transformers")) {
    $ok = Invoke-Py $VenvPy @() "import $m"
    if ($null -eq $ok) { $failed += $m }
}
if ($failed.Count) { Stop-WithError ("these packages do not load: {0}. Run again with -Rebuild." -f ($failed -join ", ")) }
Add-Result "Imports" "OK" "mediroute, fastapi, torch, faiss, sentence_transformers"

# ---------------------------------------------------------------- 7. data
Step "7. Data files"
$need = @("data\processed\hospitals.csv", "data\processed\specialties.csv", "data\processed\specialty_mapping.csv",
          "data\processed\step1_lookup.csv", "data\processed\cities.csv",
          "data\processed\vector_store\hospital_index.faiss", "data\processed\vector_store\hospital_metadata.json")
$missing = @($need | Where-Object { -not (Test-Path (Join-Path $Root $_)) })
if ($missing.Count) { Add-Result "Data" "FAIL" ("missing: {0}. Run 'git pull', or rebuild: .\.venv\Scripts\python.exe -m mediroute.data_generator.rebuild" -f ($missing -join ", ")) }
else { Add-Result "Data" "OK" "data\processed complete" }

# ---------------------------------------------------------------- 8. LLM key
Step "8. OpenRouter key (never printed)"
$key = $env:OPENROUTER_API_KEY
if (-not $key) { $key = [Environment]::GetEnvironmentVariable("OPENROUTER_API_KEY", "User") }
if ($key) { Add-Result "LLM key" "OK" "OPENROUTER_API_KEY is set" }
else {
    Add-Result "LLM key" "WARN" ('not set. Ask the account owner for your own key, then: setx OPENROUTER_API_KEY "sk-or-v1-..." ' +
        "and open a new window. Without a key the app still runs (lookup only).")
}
$key = $null

# ---------------------------------------------------------------- 9. memory
Step "9. Free memory"
try {
    $freeGb = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
    if ($freeGb -ge 2.5) { Add-Result "Free RAM" "OK" "$freeGb GB free" }
    else { Add-Result "Free RAM" "WARN" "$freeGb GB free; the backend needs about 2.5 GB. Close Teams / browser tabs before starting." }
} catch { Add-Result "Free RAM" "SKIP" "could not read" }

# ---------------------------------------------------------------- 10. ports
Step "10. Ports 8000 (backend) and 5500 (frontend)"
foreach ($port in @(8000, 5500)) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) { Add-Result "Port $port" "OK" "free"; continue }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($conn.OwningProcess)" -ErrorAction SilentlyContinue
    if ($proc -and $proc.CommandLine -match "mediroute\.backend\.main|serve_frontend\.py") {
        Add-Result "Port $port" "OK" "MediRoute already running there (start_app.ps1 restarts it)"
    } else {
        $name = if ($proc) { $proc.Name } else { "process $($conn.OwningProcess)" }
        Add-Result "Port $port" "WARN" "used by $name; close it before starting MediRoute"
    }
}

# ---------------------------------------------------------------- 11. tests
Step "11. Tests"
if ($RunTests) {
    & $VenvPy -m pytest -q
    if ($LASTEXITCODE -eq 0) { Add-Result "Tests" "OK" "all passed" }
    else { Add-Result "Tests" "FAIL" "some tests failed (see above)" }
} else {
    Add-Result "Tests" "SKIP" "skipped (run with -RunTests to check, about 1 min)"
}

# ---------------------------------------------------------------- 12. VS Code
Step "12. VS Code interpreter"
$vsDir = Join-Path $Root ".vscode"
$vsFile = Join-Path $vsDir "settings.json"
if (Test-Path $vsFile) {
    Add-Result "VS Code" "SKIP" ".vscode\settings.json exists (not changed); pick .venv via Ctrl+Shift+P > Python: Select Interpreter"
} else {
    New-Item -ItemType Directory -Force $vsDir | Out-Null
    $json = '{' + "`r`n" + '    "python.defaultInterpreterPath": "${workspaceFolder}\\.venv\\Scripts\\python.exe"' + "`r`n" + '}' + "`r`n"
    [System.IO.File]::WriteAllText($vsFile, $json)
    Add-Result "VS Code" "OK" "wrote .vscode\settings.json (uses .venv)"
}

# ---------------------------------------------------------------- 13. summary
Show-Summary
$bad = @($Results | Where-Object { $_.Status -eq "FAIL" })
Write-Host ""
if ($bad.Count) {
    Write-Host "Setup finished with problems (FAIL above)." -ForegroundColor Red
    exit 1
}
Write-Host "Setup done." -ForegroundColor Green
$keyNow = $env:OPENROUTER_API_KEY
if (-not $keyNow) { $keyNow = [Environment]::GetEnvironmentVariable("OPENROUTER_API_KEY", "User") }
if (-not $keyNow) {
    Write-Host "Next: save YOUR OpenRouter key (ask the account owner), once per laptop:" -ForegroundColor Yellow
    Write-Host '                setx OPENROUTER_API_KEY "sk-or-v1-..."' -ForegroundColor Yellow
    Write-Host "                then close this window and open a NEW one (setx only applies to new windows)." -ForegroundColor Yellow
}
$keyNow = $null
Write-Host "Start the app (from this folder: cd `"$Root`"; make sure the API key is set first):"
Write-Host "                powershell -ExecutionPolicy Bypass -File scripts\start_app.ps1"
Write-Host "  or by hand:   Terminal 1: .\.venv\Scripts\python.exe -m uvicorn mediroute.backend.main:app --host 127.0.0.1 --port 8000"
Write-Host "                Terminal 2: .\.venv\Scripts\python.exe scripts\serve_frontend.py"
Write-Host "Open:           http://127.0.0.1:5500/index.html   (admin: http://127.0.0.1:5500/admin.html)"
exit 0
