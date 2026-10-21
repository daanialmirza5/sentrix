# Test results (actual runs, 2026-10-21, Windows 11, Python 3.12.14, Node 22.23.2)

| Suite | Command | Result |
|---|---|---|
| Backend unit + API + security | `cd backend; .venv\Scripts\python.exe -m pytest` | **101 passed**, 0 failed (≈41 s; includes production-mode UI serving) |
| Frontend typecheck | `cd frontend; npx tsc -b --noEmit` | exit 0 |
| Frontend component tests (Vitest 5 + Testing Library) | `cd frontend; npx vitest run` | **12 passed** |
| Frontend production build (Vite 8, Tailwind 4) | `cd frontend; npx vite build` | built, no warnings (app 256 kB / 81 kB gzip; three.js lazy chunk 548 kB / 137 kB gzip) |
| End-to-end (Playwright 1.64, Chromium, live backend + Vite) | `cd frontend; npx playwright test` | **11 passed** (UI registration, live token revocation, Signal Lab on real engines, drift chart hover, 390 px overflow check) |
| Python dependency audit | `backend\.venv\Scripts\pip-audit.exe -r backend\requirements.txt` | No known vulnerabilities |
| npm dependency audit (all deps, incl. dev) | `cd frontend; npm audit` | **0 vulnerabilities** |
| Audit chain (demo DB) | `backend\.venv\Scripts\python.exe scripts\verify_audit.py` | valid (re-verified after the final clean reseed) |
| Drift benchmark | `backend\.venv\Scripts\python.exe scripts\eval_drift.py` | see [drift_eval.md](drift_eval.md) |

The one remaining pytest warning is a third-party deprecation notice from Starlette's TestClient about its httpx dependency. It does not come from TETHER code.

## Defects found and fixed (not hidden)
1. **Drift false alarms on benign traffic.** In-sample anchor statistics were the cause. Fixed with leave-one-out calibration and 20 enrollment windows. The held-out benign false-alarm rate is still 6.7 % at the calibrated h.
2. **The PRD claim "rolling baseline never alarms" was not reproduced.** The rolling baseline detects later (median 17.5 vs 13 windows), not never.
3. **Provenance retention purge ignored pending changes.** Sessions use `autoflush=False`, so `purge_expired` did not see unflushed expiry updates. Found by a new test; fixed by flushing first.
4. **Dependency vulnerabilities.**
   * react-router (shipped code): open-redirect advisories. Upgraded 6.28.0 → 7.18.4.
   * Dev toolchain (vitest/tinypool critical; vite/esbuild, tailwind 3 → braces/micromatch/chokidar, playwright, postcss): 18 advisories. Migrated to Vite 8, Vitest 5, Tailwind 4 (CSS-first config) and Playwright 1.64.
   * Result: 0 vulnerabilities.
5. **Frontend:**
   * missing Testing Library cleanup;
   * a 401 console error from probing `/auth/me` without a session;
   * a compile button the security role could press but the API refused;
   * a test name that did not match its assertion (renamed, and a real toast test added);
   * a weak HMAC key in a forged-token test (it produced a library warning).

6. E2E login rate limit: the suite tripped the 20/min login limiter (correct behaviour). Fixed in the test (one UI login, then cached tokens), not by loosening the limiter (ADR-012).
7. Drift chart axis used non-round ticks (13/25/38); now uses a 1-2-5 step.

8. Redesign regressions caught by tests: the Overview lost its page heading (accessibility); the 3D chunk inflated the main bundle (now lazy-loaded); the login backdrop was hidden by its overlay.

## Not run
* Docker Compose (the daemon was not running) and Redis (not installed).
* Scenarios S1–S7 and the full benchmark: not implemented, because the Trust Ladder is blocked.
* Gateway latency p50/p95/p99: there is no working inline path to measure.

## Embedding measurements (single interactive run, not a benchmark)
The reference pair "A man is eating food." / "…a piece of bread." scores 0.7553, matching the published sentence-transformers value.
Model load took 654 ms; each uncached call took 4.6–16.3 ms on 4 logical CPUs.
