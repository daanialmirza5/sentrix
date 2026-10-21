# Capture genuine screenshots from the running app (writes screenshots\*.png via the Playwright E2E suite).
# Prereqs: backend on :8000 (scripts\run_backend.ps1), Vite on :5173 (scripts\run_frontend.ps1), seed_demo.py run once.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path (Split-Path $PSScriptRoot -Parent) "frontend")
try { Invoke-RestMethod http://127.0.0.1:8000/v1/health | Out-Null } catch { throw "Backend not reachable on :8000" }
try { Invoke-WebRequest http://localhost:5173 -UseBasicParsing | Out-Null } catch { throw "Vite not reachable on :5173" }
npx playwright install chromium
npx playwright test
Write-Host "Screenshots written to $(Resolve-Path ..\screenshots)"
