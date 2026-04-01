# Stops anything listening on port 8000, then starts uvicorn with the project venv.
$ErrorActionPreference = "Continue"
$backendRoot = Split-Path -Parent $PSScriptRoot
Set-Location $backendRoot

Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    $op = $_.OwningProcess
    Write-Host "Stopping listener PID $op"
    Stop-Process -Id $op -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

$py = Join-Path $backendRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Missing venv python: $py"
    exit 1
}

$uvArgs = @("-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000")
Write-Host "Starting uvicorn (hidden window)..."
Start-Process -FilePath $py -ArgumentList $uvArgs -WorkingDirectory $backendRoot -WindowStyle Hidden
Start-Sleep -Seconds 3

try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 10
    Write-Host "OK health status:" $r.StatusCode
} catch {
    Write-Host "Health check failed:" $_.Exception.Message
    exit 1
}
