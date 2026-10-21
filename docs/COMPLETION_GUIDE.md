# Completion and deployment guide

The steps that turn this repository into a complete, deployable TETHER for judging, in order. Each step says who does it and how to tell it is done.

---

## Part A: Finish the application

### Step 1. Write the Trust Ladder policy engine (critical)
**Why:** graduated containment is the core of the problem statement. Today the gateway refuses every call (fail-closed), so TETHER detects and explains but does not contain.

**Who:** a team member, by hand. It could not be generated for this build (see [BLOCKERS.md](BLOCKERS.md)).

**File:** `backend/app/policy/trust_ladder.py`. Specification: PRD §7, TRD §5, Architecture Flow p.4.

**What it must provide:**
| Function | Behaviour (from the TRD) |
|---|---|
| `band(risk, defaults) -> int` | L0 below 30 · L1 30–54 · L2 55–74 · L3 75–89 · L4 90 and above |
| `escalate(state, session, risk, deception)` | Escalation is immediate; any deception hit goes straight to L4 |
| `record_clean_window(state, risk)` | Hysteresis: L1→L0 after 3 clean windows; L2→L1 after 5 clean windows plus owner acknowledgement; L3 needs security review; L4 is manual release only |
| `decide(level, action, hard_denies, deception) -> verdict` | L0 allow · L1 step-up for writes, egress and sensitive reads · L2 read-only, egress blocked · L3 decoy data, no side effects · L4 deny and isolate |

Persist state in the existing `AgentState` and `AgentSession` tables (`backend/app/models.py`).

**Done when:** you have unit tests for each band boundary (29/30, 54/55, 74/75, 89/90), for a deception hit going to L4, and for hysteresis.

### Step 2. Wire the engines into the gateway
**File:** `backend/app/api/routes.py` → `invoke()`. Replace the fail-closed handler with this pipeline, using functions that already exist:

1. `tokens.verify()`
2. `tools.describe()`
3. `rolefit.score()`
4. `provenance.score()`
5. `deception.inspect()`
6. `drift.drift_term()`
7. `fuse()`
8. **your** `trust_ladder.decide()`
9. `tools.execute()` only when the verdict allows it
10. `provenance.ingest()` for untrusted results
11. `chain.append()`

On L4, call `tokens.revoke_session()`; it already cascades to delegated tokens.

**Done when:** a denied action never reaches `tools.execute()` (add a test that asserts `SINK.deliveries` stays empty).

### Step 3. Alerts and incident report (FR-6, FR-14)
Add an `Alert` row whenever the level rises or a deception hit occurs. Fill its card from `fusion/explainer.py` (`why`, `factor_line`, `cause_line`, `recommendations`), and add `GET /v1/alerts` and `GET /v1/alerts/{id}/report` (JSON and Markdown).

### Step 4. Delegation graph and contagion (FR-11)
Record a `DelegationEdge` when a task is created with a parent token. Contagion: `risk_eff = max(risk, 0.5^hop × neighbour risk)`, and neighbours step up one level for a cool-down period. Expose `GET /v1/graph`.

### Step 5. The seven demo scenarios and the benchmark (PRD §12–13)
These need Steps 1–4. Write them as scripted, deterministic runs against the gateway, using the inert fixtures in `gateway/tools.py`. Then run the benchmark comparing permission-only IAM, Isolation Forest, TETHER and its ablations, and **report the measured numbers, not the targets**.

### Step 6 (optional). Behavior Engine
Implement TRD §4.2 in `backend/app/engines/behavior.py` (currently a stub returning 0), then remove `"B"` from `disabled` in `fusion/risk.py`.

### Step 7. Update the honest status
Edit the status table in `frontend/src/pages/Overview.tsx` (`PILLARS`), `docs/requirements-traceability.md` and the README banner so they match what now works.

---

## Part B: Make it deployable

### Step 8. Verify locally (about 5 minutes)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
cd backend;  .\.venv\Scripts\python.exe -m pytest              # all must pass
cd ..\frontend; npx tsc -b --noEmit; npx vitest run; npx vite build
npm audit; ..\backend\.venv\Scripts\pip-audit.exe -r ..\backend\requirements.txt
```

### Step 9. Choose a deployment target
| Option | Command | Use when |
|---|---|---|
| **Your laptop, judges in the room** | `powershell -File scripts\run_prod.ps1` | Simplest; open http://127.0.0.1:8000 |
| **Laptop on the venue network** | `powershell -File scripts\run_prod.ps1 -BindHost 0.0.0.0` | Judges use their own devices; allow port 8000 through Windows Firewall |
| **Docker / cloud VM** | `docker compose up --build` | Start Docker Desktop and test it once first; the Compose file has not been verified |
| **Cloud VM without Docker** | Install Python 3.12, uv and Node 22, then follow Step 8 and Step 9 row 2 | Any Linux VM; put a reverse proxy with TLS in front |

### Step 10. Production settings
Create a `.env` from `.env.example`. **Never commit it.**
- `TETHER_DEMO_PASSWORD`: change it from `tether-demo` if the site is public.
- `TETHER_CORS_ORIGINS`: set your real URL if the UI is served elsewhere.
- Back up `data/keys/`. Those keys sign the contracts; if you lose them, existing signatures stop verifying.

### Step 11. First run on the deployment machine
```powershell
powershell -File scripts\run_prod.ps1
backend\.venv\Scripts\python.exe scripts\seed_demo.py     # once, in a second window
```
The first setup needs internet access for the 90 MB MiniLM model download. Do it before the event.

### Step 12. Just before judging
```powershell
# stop the server first
backend\.venv\Scripts\python.exe scripts\reset_demo.py --yes
powershell -File scripts\run_prod.ps1
backend\.venv\Scripts\python.exe scripts\seed_demo.py
```
Running the Playwright suite adds test agents to the demo data, so reset after any test run.

---

## Part C: Submission

### Step 13. Presentation deck
In `TETHER_Hackathon_Final.pptx`, replace `[ADD TEAM NAME HERE]`, `[ADD COLLEGE NAME HERE]`, `[ADD P.S. HERE]` and the member names and contact numbers. Add screenshots from `screenshots/`.

### Step 14. Fallback recording
Record a 3–5 minute screen video of the README's evaluator tour, in case the venue machine or network fails.

### Step 15. Repository visibility
The GitHub repo is **private**. When you are ready to share it with judges:
```powershell
gh repo edit daanialmirza5/tether --visibility public --accept-visibility-change-consequences
```
or keep it private and invite a judge by GitHub username (they receive an email invitation):
```powershell
gh api -X PUT repos/daanialmirza5/tether/collaborators/JUDGE_USERNAME -f permission=pull
```

### Step 16. Rehearse the hard question
"Where is the containment?" Answer honestly with whatever state Steps 1–5 reached. The Overview page already shows the live status of each pillar.

---

## Checklist
- [ ] 1 Trust Ladder written and unit-tested
- [ ] 2 Gateway pipeline wired; denied actions provably never execute
- [ ] 3 Alerts and incident reports
- [ ] 4 Delegation graph and contagion
- [ ] 5 Scenarios S1–S7 and measured benchmark
- [ ] 6 (optional) Behavior Engine
- [ ] 7 Status table, traceability matrix and README updated
- [ ] 8 All tests and audits green
- [ ] 9–11 Deployed and seeded on the target machine
- [ ] 12 Fresh reset right before judging
- [ ] 13 Deck placeholders filled
- [ ] 14 Fallback video recorded
- [ ] 15 Repo visibility or collaborators set
- [ ] 16 Rehearsed
