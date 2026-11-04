param(
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 8000,
    [string]$Model = "llama3.2",
    [switch]$SkipOllama
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$logDir = Join-Path $repoRoot "logs"
$medirouteLog = Join-Path $logDir "mediroute.log"
$backendStdoutLog = Join-Path $logDir "backend_restart_stdout.log"
$backendStderrLog = Join-Path $logDir "backend_restart_stderr.log"

Write-Host "[1/6] Checking Python venv at $venvPython"
if (-not (Test-Path $venvPython)) {
    throw "Python venv not found at $venvPython. Activate the project environment first."
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Test-OllamaHealthy {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 5 -UseBasicParsing
        return ($response.StatusCode -eq 200)
    }
    catch {
        return $false
    }
}

function Test-OllamaModelAvailable {
    param(
        [string]$ModelName
    )

    if (-not $ModelName) {
        return $false
    }

    $list = & $ollamaExec list 2>$null
    foreach ($line in $list) {
        if ($line -match '^NAME\s') {
            continue
        }

        if (-not $line.Trim()) {
            continue
        }

        $firstToken = ($line -split '\s+')[0]
        if ($firstToken -eq $ModelName -or $firstToken -like ($ModelName + ':*')) {
            return $true
        }
    }

    return $false
}

function Stop-ProjectProcesses {
    Write-Host "[2/6] Stopping existing app and Ollama processes"
    $targets = @(
        "uvicorn mediroute.backend.main:app",
        "python.exe",
        "ollama serve"
    )

    $processes = Get-CimInstance Win32_Process | Where-Object {
        $cmd = $_.CommandLine
        $matchesProject = $cmd -match [regex]::Escape($repoRoot)
        $matchesBackend = $cmd -match "uvicorn.*src\.Src\.backend\.main:app"
        $matchesOllama = $cmd -match "ollama.*serve"
        $matchesPython = $cmd -match "python.*MediRoute"
        $matchesProject -or $matchesBackend -or $matchesOllama -or $matchesPython
    }

    foreach ($proc in $processes) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Host "Stopped process $($proc.ProcessId): $($proc.CommandLine)"
        }
        catch {
            Write-Host "Could not stop $($proc.ProcessId); continuing..."
        }
    }

    Write-Host "[3/6] Deleting old log files before startup"
    if (Test-Path $medirouteLog) {
        Remove-Item $medirouteLog -Force
        Write-Host "Deleted existing log file: $medirouteLog"
    }

    if (Test-Path $backendStdoutLog) {
        Remove-Item $backendStdoutLog -Force
    }

    if (Test-Path $backendStderrLog) {
        Remove-Item $backendStderrLog -Force
    }
}

function Start-OllamaIfNeeded {
    if ($SkipOllama) {
        Write-Host "[4/6] Skipping Ollama startup because -SkipOllama was provided."
        return
    }

    Write-Host "[4/6] Detecting Ollama executable"
    $ollamaExec = @(
        "C:\Users\pravi\AppData\Local\Programs\Ollama\ollama.exe",
        "C:\Users\pravi\AppData\Local\Programs\Ollama\ollama.cmd",
        "C:\Users\pravi\AppData\Local\Programs\Ollama\ollama"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

    if (-not $ollamaExec) {
        $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
        if (-not $ollamaCmd) {
            throw "Ollama is not installed or not on PATH. Install it from https://ollama.com/download"
        }
        $ollamaExec = $ollamaCmd.Source
    }

    $ollamaProcesses = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match "ollama" -or $_.CommandLine -match "ollama.*serve"
    }

    foreach ($proc in $ollamaProcesses) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Host "Stopped stale Ollama process $($proc.ProcessId)"
        }
        catch {
            Write-Host "Could not stop stale Ollama process $($proc.ProcessId)"
        }
    }

    Write-Host "[5/6] Starting Ollama service: $ollamaExec serve"
    Start-Process -FilePath $ollamaExec -ArgumentList "serve" -WorkingDirectory $repoRoot -WindowStyle Hidden

    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        if (Test-OllamaHealthy) {
            break
        }
        Start-Sleep -Seconds 1
    }

    if (-not (Test-OllamaHealthy)) {
        throw "Ollama did not become healthy after startup."
    }

    Write-Host "Ollama is healthy on http://127.0.0.1:11434"

    $hasModel = Test-OllamaModelAvailable -ModelName $Model

    if (-not $hasModel) {
        Write-Host "[5/6] Pulling Ollama model: $Model"
        & $ollamaExec pull $Model
    }
    else {
        Write-Host "[5/6] Ollama model already available: $Model"
    }

    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $ready = Test-OllamaModelAvailable -ModelName $Model
        if ($ready) {
            Write-Host "Ollama model is ready: $Model"
            break
        }
        Start-Sleep -Seconds 2
    }

    if (-not (Test-OllamaModelAvailable -ModelName $Model)) {
        throw "Ollama model $Model is not available after pull."
    }
}

function Start-Backend {
    Write-Host "[6/6] Starting backend: python -m uvicorn mediroute.backend.main:app --host ${ListenHost} --port ${Port}"

    $backendArgs = @(
        "-m",
        "uvicorn",
        "mediroute.backend.main:app",
        "--host",
        $ListenHost,
        "--port",
        $Port.ToString()
    )

    $process = Start-Process -FilePath $venvPython -ArgumentList $backendArgs -WorkingDirectory $repoRoot -RedirectStandardOutput $backendStdoutLog -RedirectStandardError $backendStderrLog -PassThru

    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri "http://${ListenHost}:${Port}/api/health" -Method Get -TimeoutSec 5 -UseBasicParsing
            if ($response.StatusCode -eq 200) {
                Write-Host "Backend is healthy on http://${ListenHost}:${Port}"
                return
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    throw "Backend did not become healthy on http://${ListenHost}:${Port} within 30 seconds."
}

Write-Host "Restarting Mediroute app..."
Stop-ProjectProcesses

if (-not $SkipOllama) {
    Start-OllamaIfNeeded
}

Start-Backend

Write-Host "Restart complete. Swagger URL: http://${ListenHost}:${Port}/docs"
