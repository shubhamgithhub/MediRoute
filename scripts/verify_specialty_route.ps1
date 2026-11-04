$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
$uri = "http://127.0.0.1:8130/api/health"

$process = Start-Process -FilePath $py -ArgumentList @('-m','uvicorn','mediroute.backend.main:app','--host','127.0.0.1','--port','8130') -WorkingDirectory $root -PassThru -NoNewWindow

$success = $false
for ($i = 0; $i -lt 40; $i++) {
    try {
        $r = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { $success = $true; break }
    }
    catch {
        Start-Sleep -Seconds 1
    }
}

if (-not $success) {
    Write-Error "Server did not start on port 8130"
    Stop-Process -Id $process.Id -Force
    exit 1
}

$payload = @{
    requirement = "my knee is paining"
    location = "Bengaluru"
    language = "English"
    additionalPreference = ""
    reportName = @()
} | ConvertTo-Json -Compress

try {
    $response = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8130/api/analyze" -ContentType "application/json" -Body $payload
    $response | ConvertTo-Json -Depth 10
    Write-Host "`n--- LOG TAIL ---"
    Get-Content -Path (Join-Path $root "logs\mediroute.log") -Tail 30
}
finally {
    Stop-Process -Id $process.Id -Force
}
