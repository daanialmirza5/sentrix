# Architecture decision records

**ADR-001: Python 3.12 instead of 3.11.** Only 3.12–3.14 were installed; 3.12 (via uv) is the closest to the TRD's version.

**ADR-002: ONNX Runtime instead of sentence-transformers/PyTorch.** Windows Application Control blocked `torch_python.dll`. The same all-MiniLM-L6-v2 weights (official ONNX export) run through ONNX Runtime, with mean pooling and L2 normalisation identical to sentence-transformers. This was verified against the reference similarity of 0.7553. If the model can't load, a hashed bag-of-words fallback is used and reported as `lexical-fallback` in `/v1/health`; it is never shown as MiniLM.

**ADR-003: Inert test markers.** Fixtures contain `[[TETHER-TEST-INJECTION: …]]` rather than realistic attack text, chosen by the project owner after a classifier block. Outbound "transfers" go to `MockSink` on the reserved `mock-sink.invalid` host. The tool module has no network or file I/O imports, and a test enforces this.

**ADR-004: Deception hit goes to L4 (PRD Flow A vs TRD conflict).** PRD Flow A shows L3 at the honey-resource step; TRD §5 says any deception hit goes straight to L4. The TRD is followed. This is moot in this build because the policy engine is blocked.

**ADR-005: Frozen anchor enrollment.** The anchor is fitted on the first 20 clean 10-action windows after registration, then frozen and signed (tether-system Ed25519). d_mean and d_std use leave-one-out estimates, because in-sample estimates produced benign false alarms (measured). h is a calibration parameter, as the TRD says. `scripts/eval_drift.py` calibrates it on seeds 0–9 and reports on 10–39.

**ADR-006: Contract version 1 is published directly; later versions only come from approved change requests.** This is enforced in `registry.publish_initial` (409 if a contract exists). Approval requires the security role and a different person from the requester, and both the change request and the new version are signed.

**ADR-007: Schema via `metadata.create_all`.** No migration tool is used for the MVP. The schema is created on startup; `scripts/reset_demo.py` removes only the demo DB.

**ADR-008: Gateway fails closed without the policy engine.** The TRD fail policy is "fail closed for sensitive scopes if scoring is unavailable". Because no verdict can be produced at all, every scope fails closed (HTTP 503), and the attempt is written to the audit log first. No placeholder policy (allow-all or deny-all) is presented as the Trust Ladder.

**ADR-009: Behavior signal disabled.** It is fixed at 0, and fusion lists B under `disabled`, so contributions never present it as a measured zero.

**ADR-010: Demo authentication.** The four PRD personas share one password from `TETHER_DEMO_PASSWORD`. Operator JWTs (HS256) use a secret separate from the broker's Ed25519 task-token key. This is not an enterprise IdP.

**ADR-011: Signal Lab (`POST /v1/analyze`) is analysis only.** It runs the real role-fit, deception, provenance-attribution and fusion code on a hypothetical action, against the agent's verified contract. It never executes a tool, writes no rows and appends no audit events (tested). It returns no trust level, because level mapping belongs to the blocked policy engine. The S signal is approximated as max(action sensitivity, payload DLP sensitivity) × destination risk (0.05 for allowlisted or internal hosts, 1.0 otherwise) for egress, and 0.5 × sensitivity for out-of-domain reads. Full canary values are never returned (masked only, tested).

**ADR-012: The E2E suite respects the login rate limit.** Rather than loosening the 20/min limiter for tests, the suite signs in through the UI once and reuses one cached API token per persona.
