# One-process production run: builds the console and serves UI + API from http://127.0.0.1:8000
# Usage: powershell -File scripts\run_prod.ps1   (add -Host 0.0.0.0 to expose on the LAN)
param([string]$BindHost = "127.0.0.1", [int]$Port = 8000)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Push-Location (Join-Path $root "frontend"); npx vite build; Pop-Location
Set-Location (Join-Path $root "backend")
Write-Host "TETHER console + API on http://$($BindHost):$Port  (API docs: /docs)"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host $BindHost --port $Port
