# Entry point for Windows Task Scheduler: makes sure Ollama is up, runs the agent, keeps a log.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8  # read Python's UTF-8 output correctly
New-Item -ItemType Directory -Force "$root\logs" | Out-Null
$log = "$root\logs\$(Get-Date -Format yyyy-MM-dd_HHmm).log"

function Test-Ollama {
    try { (Invoke-WebRequest http://localhost:11434 -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 } catch { $false }
}

if (-not (Test-Ollama)) {
    "Ollama not running; starting it" | Out-File $log -Append -Encoding utf8
    Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
    for ($i = 0; $i -lt 30 -and -not (Test-Ollama); $i++) { Start-Sleep -Seconds 2 }
}

& "$root\.venv\Scripts\python.exe" -m agent.main @args *>&1 | Out-File $log -Append -Encoding utf8
$code = $LASTEXITCODE

# Keep 30 days of logs
Get-ChildItem "$root\logs\*.log" | Where-Object LastWriteTime -lt (Get-Date).AddDays(-30) | Remove-Item
exit $code
