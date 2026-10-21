# Requirements traceability matrix

Status key:
* **PASS**: implemented, with an automated test that ran and passed in this environment.
* **PARTIAL**: some of the requirement is implemented and tested; the rest is missing (stated in Notes).
* **BLOCKED**: could not be written because a safety classifier stopped the write (see [BLOCKERS.md](BLOCKERS.md)).
* **NOT IMPLEMENTED**: not built.
* **UNVERIFIED**: written but never executed here.

Test results referenced here are from the runs recorded in [reports/test-results.md](../reports/test-results.md).

## Functional requirements (PRD §5)

| ID | Requirement (short) | Source | Module | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| FR-1 | Register agent; Role Contract JSON/YAML; Contract Compiler with human review | PRD §5, TRD §3.1 | `contracts/schema.py`, `contracts/registry.py`, `contracts/compiler.py`, `api/routes.py` | `test_contracts.py` (all), `test_api.py::test_end_to_end_contract_and_change_request`, E2E `contract versions…` | **PASS** | Signatures: Ed25519 owner + security. The compiler refuses high-risk tools and prompt-requested authority. |
| FR-2 | Mediate all tool calls via gateway; allow/redact/deny/route | PRD §5 | `api/routes.py::invoke`, `gateway/tools.py` | `test_api.py` (fail-closed, 413, 422) | **PARTIAL** | The endpoint exists but always **fails closed** (HTTP 503, audited, nothing executes) because the policy engine is blocked. The simulated tool layer and redaction exist and are unit-tested, but they are not reachable through the gateway. |
| FR-3 | Per-task short-lived credentials, scope = contract ∩ task (∩ parent) | PRD §5, TRD §3.3 | `broker/tokens.py`, `POST /v1/tasks` | `test_tokens_audit.py` (11 tests), `test_api.py` | **PARTIAL** | Minting, EdDSA verification, expiry, revocation, binding, contract-version binding, TTL cap and descendant cascade all PASS. Enforcement at a working gateway is missing. |
| FR-4 | Trust labels; taint tracking; link action to source span | PRD §5, TRD §4.3 | `engines/provenance.py` | `test_attribution_finds_marker_line`, `test_clean_doc_attribution_uncertain`, `test_taint_decay`, `test_trusted_ingest_opens_no_window`, 4 retention/decay tests in `test_gaps.py` | **PARTIAL** | The engine works (it finds page 2 line 14 of the inert fixture and reports uncertainty on clean documents) but is not wired into a live gateway. |
| FR-5 | Real-time R, B, P, S per action | PRD §5, TRD §4.1–4.2 | `engines/rolefit.py`, `engines/provenance.py`, `engines/behavior.py` (stub) | `test_engines.py` role-fit tests | **PARTIAL** | R is PASS (rules + MiniLM; a semantic score cannot override a deny, which is tested). P is unit-only. S has no dedicated engine; the inputs exist (sensitivity table, DLP). **B is NOT IMPLEMENTED** (stub returns 0). None of this runs per action in real time. |
| FR-6 | Noisy-OR fusion 0–100, contributions sum to 100 %, plain-English explanation | PRD §8, TRD §4.8 | `fusion/risk.py`, `fusion/explainer.py` | `test_fusion_*` (3 tests) | **PARTIAL** | Fusion and the explainer are PASS (reproducibility, override labels, recommendations: `test_gaps.py`). Neither runs on live traffic. |
| FR-7 | Trust Ladder L0–L4, hysteresis, step-up, manual override | PRD §5, TRD §5 | none | none | **BLOCKED** | BLOCKERS.md #3. |
| FR-8 | Honey-resources, canaries, egress DLP, critical alert on hit | PRD §5, TRD §4.5 | `engines/deception.py` | `test_honey_and_canary`, `test_canaries_unique_per_agent` | **PARTIAL** | Detection is PASS. The "instant critical alert" and containment depend on the blocked policy engine and the missing alert pipeline. |
| FR-9 | Frozen anchor + CUSUM per agent | PRD §5, TRD §4.4 | `engines/drift.py`, `scripts/eval_drift.py` | `test_cusum_frozen_anchor_properties`, `test_tampered_anchor_detected`, drift benchmark | **PARTIAL** | The engine and a signed anchor are PASS. Not fed by live traffic. Measured held-out benign false-alarm rate is 6.7 % ([reports/drift_eval.md](../reports/drift_eval.md)). |
| FR-10 | Signed Role Change Request; version bump; anchor reset; probation | PRD §5, TRD §5 | `contracts/registry.py`, CR API, `ChangeRequests.tsx` | 6 unit tests, API test, E2E approval flow | **PARTIAL** | Submit, sign, two-person approve/reject, tamper and stale-base rejection, and versioning all PASS. The probation counter is set, but nothing consumes it. `drift.reset_for_new_version` exists but is not called. |
| FR-11 | Delegation graph, attenuation, risk contagion | PRD §5, TRD §4.7 | `broker/tokens.py` (cascade, intersection) | `test_revocation_cascades_to_descendants`, `test_scope_intersection` | **PARTIAL** | Token-level attenuation and cascade are PASS; manual revocation with cascade is available in the API and UI (security role, audited; `test_new_endpoints.py`, E2E). There is no graph service or contagion (NetworkX unused), and no `/v1/graph`. |
| FR-12 | Canary-Instruction heartbeat, ISI | PRD §5, TRD §4.6 | `engines/canary.py` | `test_isi` | **PARTIAL** | ISI (Beta posterior) and the tightening rules are PASS. There is no shadow-lane runner or simulated agents. |
| FR-13 | Sandbox mode serving decoys | PRD §5 | `engines/deception.py::decoy_content` | `test_honey_and_canary` (decoy content) | **NOT IMPLEMENTED** | Decoy generation exists; sandbox routing needs the blocked policy engine. |
| FR-14 | Hash-chained audit log; exportable incident report | PRD §5, TRD §3.2 | `audit/chain.py`, `scripts/verify_audit.py` | 4 chain tests (modify, delete, full rewrite vs anchor), E2E verify | **PARTIAL** | The chain is PASS. **Incident report export is NOT IMPLEMENTED** (there are no alerts to report on). |
| FR-15 | Dashboard: fleet, timeline, alert cards, graph, one-click actions | PRD §5 | `frontend/src` | 12 Vitest tests, 11 Playwright E2E | **PARTIAL** | Overview (status bar, recent activity), Agents, Contracts (verify / diff / export / compile), Change Requests (approve with confirmation, toasts), Audit (expandable hash links), Credentials (list and revoke), Signal Lab (what-if engine analysis), Drift (measured CUSUM chart and table), agent registration and the mobile layout are PASS (12 Vitest, 11 Playwright). Timeline, alerts, graph, and restrict/isolate actions are NOT IMPLEMENTED. |

## Non-functional and other requirements

| Area | Status | Evidence / notes |
|---|---|---|
| Inline latency < 50 ms p95 | **NOT MEASURED** | There is no working inline path. The only measurement is MiniLM per embedding: 4.6–16 ms, single runs, see the transcript in reports/test-results.md. |
| Fail-safe policy | **PARTIAL** | The gateway fails closed for *all* scopes. There is no fail-open for low-risk reads, because that needs the policy engine. |
| Privacy (hashes by default, retention) | **PARTIAL** | Audit stores hashes and metadata, and canaries are masked in the API. Provenance retention purge is PASS (`test_gaps.py`: expired raw spans dropped, hash kept, flagged cause span kept). |
| Explainability (contributions sum to 100 %) | **PASS** (unit) | `test_fusion_noisy_or_and_contributions` |
| FPR < 2 % benign | **NOT MEASURED** | There is no end-to-end benchmark. |
| Self-protection (signed contracts/anchors, chain, separate creds) | **PASS** (unit) | Contract tamper, anchor tamper, chain tamper; operator JWT secret is separate from the broker key. |
| Portability (CPU-only, local) | **PASS** | Runs on this machine with ONNX Runtime on CPU, without PyTorch (which is blocked by Windows Application Control, ADR-002). |
| API (TRD §6) | **PARTIAL** | Implemented: agents, compile, versions, change requests (+approve/reject), tasks, gateway/invoke (fail-closed), audit verify/events/anchor, health. Additional: `/v1/tokens` (+revoke), `/v1/analyze` (analysis only, ADR-011), `/v1/reports/drift`. Missing: `/v1/events`, `/v1/agents/{id}/risk`, `/timeline`, `/alerts`, `/agents/{id}/response`, `/graph`, `WS /v1/stream`. |
| Demo scenarios S1–S7 | **NOT IMPLEMENTED** | All seven need a working gateway and policy. The poisoned-document fixture (inert marker) exists and its attribution is unit-tested. |
| Benchmark (6 attacks, IAM / IsolationForest / ablations) | **NOT IMPLEMENTED** | Only the drift-pillar benchmark ran. |
| Behavior Engine (TRD §4.2) | **NOT IMPLEMENTED** | Disabled stub; BLOCKERS.md #2. |
| Redis Streams | **UNVERIFIED / NOT IMPLEMENTED** | Redis isn't installed. No Redis bus code exists; health reports the in-process mode. |
| Docker Compose | **UNVERIFIED** | Files written; the Docker daemon was not running. |
| Dependency vulnerabilities | **PASS** | `pip-audit` and `npm audit`: 0 known vulnerabilities on the last run |
| Sandbox safety (no real network, isolated VFS) | **PASS** | `test_tools_module_has_no_network_or_file_io` (AST import scan), `test_http_post_goes_to_mock_sink_only`, path-traversal tests. |
