# TETHER

**Live demo:** https://tether-production-81af.up.railway.app (sign in as `priya` / `tether-demo`)

**Valid token ≠ valid behavior.** IAM asks "is this identity allowed to do this?" TETHER asks "is this still you?"

TETHER binds each AI agent to a signed Role Contract and is designed to score every tool call against it, then contain drift with a five-level Trust Ladder (D3COY 2026, Round 0).

> **Build status: incomplete.** Four writes were stopped by a safety classifier during the build ([docs/BLOCKERS.md](docs/BLOCKERS.md)). The **Trust Ladder policy engine is not implemented**, so the gateway **fails closed**: every tool call is denied (HTTP 503) and audited. The **Behavior Engine is a disabled stub** (s_b = 0). The seven demo scenarios and the full benchmark are not implemented. See the [traceability matrix](docs/requirements-traceability.md) for per-requirement status, and the [completion and deployment guide](docs/COMPLETION_GUIDE.md) for the remaining steps.

## What works (tested)
* **Signed Role Contracts**: JSON/YAML, schema validation, Ed25519 owner + security signatures, tamper detection, export, version diff.
* **Contract Compiler**: drafts from a manifest and prompt, records the evidence for each inference, refuses high-risk tools and prompt-requested authority, and requires human review.
* **Signed Role Change Requests**: owner submits, a *different* security approver signs; alteration and stale-base checks; versions only move through this path.
* **Task-bound credentials**: EdDSA JWTs, scope = contract ∩ task (∩ parent), expiry, revocation with descendant cascade, contract-version binding.
* **Hash-chained audit log**: detects modification, deletion, and full rewrite (via the anchored head).
* **Engines, unit-tested in isolation**: role-fit (rules + MiniLM via ONNX; a semantic score cannot override a deny), provenance taint and span attribution, deception (honey-resources, per-agent canaries, DLP), frozen-anchor CUSUM drift, heartbeat ISI, noisy-OR fusion.
* **Console** (React 18, TypeScript, Vite 8, Tailwind 4, three.js): a 3D constellation of agents tethered to the gateway (WebGL, with a 2D fallback and reduced-motion support), a live status bar, overview with recent activity, agents, contracts (verify / diff / export / compile), change requests (confirmation dialog and toasts), and an audit log with expandable hash links, **Credentials** (list and revoke task tokens, with cascade), **Signal Lab** (what-if scoring of an action with the real engines; nothing executes), **Drift** (measured CUSUM chart), and agent registration. It is responsive down to 390 px.
* **Dependencies**: `pip-audit` and `npm audit` both report 0 known vulnerabilities (last run).

## Run it for judging (one process, one URL)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1     # first time only
powershell -File scripts\run_prod.ps1                          # builds the console, serves UI + API on http://127.0.0.1:8000
backend\.venv\Scripts\python.exe scripts\seed_demo.py           # in a second window, once: the synthetic PRD fleet
```
Open **http://127.0.0.1:8000** and sign in as `priya` with the password `tether-demo`. Add `-BindHost 0.0.0.0` to `run_prod.ps1` to expose it on your network.

**A 5-minute tour for evaluators:** Overview (3D fleet constellation and the honest pillar status) → Signal Lab ("Out-of-role read 1 step after poisoned quote" → Analyse: role-fit deny rule, honey-resource, taint, cause = page 2 line 14) → Change Requests (as Meera submit, as Priya approve, and a new signed contract version appears) → Role Contracts (signatures and diff) → Credentials (revoke a token) → Drift (measured CUSUM) → Audit Log (verify the hash chain).

## Windows setup (development mode)
Prerequisites: [uv](https://docs.astral.sh/uv/), Node 22+, Git. No Docker, Redis or GPU needed.
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   # venv (Python 3.12), deps, MiniLM ONNX model, npm install
powershell -File scripts\run_backend.ps1                     # terminal 1: http://127.0.0.1:8000  (API docs: /docs)
powershell -File scripts\run_frontend.ps1                    # terminal 2: http://localhost:5173
backend\.venv\Scripts\python.exe scripts\seed_demo.py         # terminal 3: seed the synthetic fleet
```
Sign in as `priya` (security), `meera` (owner), `arjun` (admin) or `auditor` (read-only). The password is `TETHER_DEMO_PASSWORD`, default `tether-demo` (see `.env.example`).

Linux/macOS: same steps, using `backend/.venv/bin/python`. Not tested.

## Tests
```powershell
cd backend;  .\.venv\Scripts\python.exe -m pytest        # 97 tests: unit, API, security
cd frontend; npx tsc -b --noEmit; npx vitest run          # typecheck + 12 component tests
cd frontend; npx playwright install chromium; npx playwright test   # 11 E2E (incl. mobile); needs backend + Vite + seed
```
The E2E suite files and approves a real change request, so the demo contract version increments on each run.
Results from the final run are in [reports/test-results.md](reports/test-results.md).

## Other commands
| Task | Command |
|---|---|
| Verify the audit chain (offline) | `backend\.venv\Scripts\python.exe scripts\verify_audit.py` |
| Drift benchmark (synthetic) | `backend\.venv\Scripts\python.exe scripts\eval_drift.py` writes `reports/drift_eval.{json,md}` |
| Reset the demo DB only (stop the backend first) | `backend\.venv\Scripts\python.exe scripts\reset_demo.py --yes` |
| Screenshots | `powershell -File scripts\capture_screenshots.ps1` writes `screenshots/` ([index](screenshots/INDEX.md)) |
| Dependency audit | `uv pip install --python backend\.venv\Scripts\python.exe pip-audit; backend\.venv\Scripts\pip-audit.exe -r backend\requirements.txt; cd frontend; npm audit` (both clean on the last run) |
| GNU make users | `make install`, `make test`, `make e2e`, … (see `Makefile`) |

## Docker
The root `Dockerfile` builds a single container (API + console + MiniLM model) and is **verified**: built and smoke-tested locally (health, seeded fleet, UI deep links, real MiniLM analysis, audit chain). It listens on `$PORT` and seeds the demo fleet on first start (`TETHER_AUTO_SEED=1`).
```powershell
docker build -t tether .
docker run -p 8000:8000 tether        # http://127.0.0.1:8000
```
`railway.json` deploys the same image to Railway (`railway up`). The older two-service `docker-compose.yml` is still unverified.

## Measured results
* **Drift (synthetic, held-out seeds, calibrated h = 10):** frozen anchor detects 100 % with a median 13-window delay; the rolling baseline also detects, with a median 17.5. The benign false-alarm rate is **6.7 %**. Full table: [reports/drift_eval.md](reports/drift_eval.md).
* No detection-rate, FPR, latency or continuity numbers exist for the full system. The PRD targets (≥90 % TPR, <2 % FPR, <50 ms p95) are **unmeasured**.

## Known limitations
See [docs/BLOCKERS.md](docs/BLOCKERS.md), [docs/security.md](docs/security.md) and [docs/decisions.md](docs/decisions.md). In short: no runtime enforcement, no behavior signal, no delegation graph or contagion, no alerts or incident reports, no WebSocket stream, no Redis, no scenarios, and the synthetic data only.

## Repository
```
backend/app/   api, audit, broker, contracts, engines, fusion, gateway, security, services
backend/tests/ unit/, api/
frontend/      src/ (pages, components, services), tests/ (Vitest), e2e/ (Playwright)
scripts/       setup.ps1, run_*.ps1, seed_demo.py, reset_demo.py, verify_audit.py, eval_drift.py, download_model.py
docs/          architecture, decisions, security, requirements-traceability, BLOCKERS
reports/       test-results.md, drift_eval.*
screenshots/   14 real captures + INDEX.md
```
