# TETHER Windows setup. Run from the repo root:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv is required: https://docs.astral.sh/uv/" }
Write-Host "== Backend (Python 3.12 venv)"
uv venv backend\.venv --python 3.12
uv pip install --python backend\.venv\Scripts\python.exe -r backend\requirements.txt

Write-Host "== MiniLM ONNX model"
backend\.venv\Scripts\python.exe scripts\download_model.py

Write-Host "== Frontend"
Push-Location frontend; npm install --no-audit --no-fund; Pop-Location

Write-Host "Done. Next: scripts\run_backend.ps1, scripts\run_frontend.ps1, then scripts\seed_demo.py"
