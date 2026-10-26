# Screenshot index

All images were captured by Playwright (`frontend/e2e/console.spec.ts`) from the running application (FastAPI on :8000, Vite on :5173), 1440×900 (plus one 390×844 mobile capture), dark scheme. Data is synthetic, seeded by `scripts/seed_demo.py`.

| File | What it proves |
|---|---|
| `01-login.png` | Demo operator login with persona selection; no credentials shown in the UI. |
| `02-overview.png` | Live health from `/v1/health`: degraded state, gateway failing closed, Behavior Engine and Trust Ladder shown as not implemented, audit chain verified. |
| `03-agents.png` | Seeded fleet with signed contract versions and masked canaries. |
| `04-change-request-pending.png` | Owner (Meera) sees a pending, signed request and has no approve control. |
| `05-approval-confirm.png` | Security approver confirmation dialog before signing. |
| `06-change-request-approved.png` | Approval produced a new contract version. |
| `07-contract-versions-diff.png` | Version history, both signatures verified, and the diff of the approved change. |
| `08-contract-compiler.png` | Compiler output: inferred permissions with evidence; prompt overreach and `http.post` "NOT granted". |
| `09-audit-verified.png` | Browser-triggered hash-chain verification; an expanded row shows the event details and its `prev_hash` → `hash` link. |
| `10-mobile-overview.png` | 390 px phone layout. The E2E asserts there is no horizontal page overflow. |
| `11-register-agent-secret.png` | Agent registered from the UI; the one-time secret is shown once (only its hash is stored). |
| `12-credentials-revoke.png` | Security approver revoking a live task token minted during the test; the reason is audited. |
| `13-signal-lab.png` | Real engines on the poisoned-quote action: deny-list rule, honey-resource, taint, attribution to page 2 line 14, noisy-OR contributions, Behavior shown as disabled, no trust level. |
| `14-drift.png` | Measured CUSUM trace (held-out seed 10) for the frozen anchor vs the rolling baseline with threshold h, hover readout, and the results table. |

Not captured, because the features do not exist: alerts, timeline, delegation graph, heartbeat, simulator, full benchmark page.
| `15-live-deployment.png` | The public Railway deployment (https://sentrix-production.up.railway.app), signed in, with the MiniLM engine active and the auto-seeded fleet. Browser console: zero errors. |
