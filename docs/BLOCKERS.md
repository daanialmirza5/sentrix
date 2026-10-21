# Build blockers log

| # | Date | Operation | Outcome | Status |
|---|------|-----------|---------|--------|
| 1 | 2026-10-21 | Writing the simulated tool layer with realistic attack-text fixtures | Stopped by a safety classifier | Resolved: the owner chose inert `[[TETHER-TEST-INJECTION: ...]]` markers and a mock `.invalid` destination. `backend/app/gateway/tools.py` was rewritten that way. |
| 2 | 2026-10-21 | Writing `backend/app/engines/behavior.py` (Behavior Engine) | Stopped by a safety classifier | Owner chose Option 3. `behavior.py` is now a disabled stub (s_b = 0, `BEHAVIOR_ENGINE_ENABLED` has no effect). Behavior Engine status: **NOT IMPLEMENTED**. |
| 3 | 2026-10-21 | Writing `backend/app/policy/trust_ladder.py` (Trust Ladder policy engine, FR-7) | Stopped by a safety classifier | **Open.** The file was not created. This is on the critical path: the gateway, containment, contagion, scenarios and most tests depend on it. |

| 4 | 2026-10-21 | Writing `frontend/src/pages/ReferenceAttack.tsx` (step-by-step replay page for PRD Flow A) | Stopped by a safety classifier | **Open / not retried.** The page does not exist. The backend option it would have used (`payload_from_honey` on `/v1/analyze`) exists and is tested; individual steps can be analysed one at a time in Signal Lab. |

## Impact of #3
Without the policy engine there are no verdicts or levels. The gateway pipeline, the delegation
contagion, the scenario runner, the API response actions and the dashboard's trust views cannot be
completed honestly. A stub was not used here: a no-op policy would either allow everything, which
breaks "never execute a denied action", or deny everything, which is not TETHER.

## Decision after #3 (owner: "continue until you finish")
The Trust Ladder was not rewritten in any form. Everything that does not depend on it was finished and
tested, and the gateway fails closed (TRD fail policy, ADR-008). Still not built because they depend on the
policy engine: the live gateway pipeline, alerts and incident reports, the delegation graph and contagion,
sandbox mode, the scenario runner (S1-S7), the full benchmark, the WebSocket stream, and the dashboard
pages for those.

Current verified state: [reports/test-results.md](../reports/test-results.md). Per-requirement status:
[requirements-traceability.md](requirements-traceability.md).

## How to unblock
Add `backend/app/policy/trust_ladder.py` (written by a person) exposing:
`band(risk) -> level`, `effective_level(agent_state, session) -> level`, escalation and de-escalation with the
TRD hysteresis rules, and `decide(level, action, hard_denies, deception) -> verdict`. Then wire the engines
into `api/routes.py::invoke` in place of the fail-closed handler.
