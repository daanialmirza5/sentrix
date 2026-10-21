# Security notes and threat model

## Trust boundaries
1. **Agent ↔ gateway.** Agents hold only task-bound EdDSA tokens, never raw tool credentials. Tokens bind agent, task, session, scope and contract version, and their TTL is clamped to 5–15 min.
2. **Operator ↔ API.** Operator JWT with role checks (viewer / owner / security / admin), signed with a secret separate from the broker key.
3. **TETHER ↔ storage.** SQLite plus a hash-chained audit log; the chain head is anchored to a separate file.
4. **Simulation ↔ host.** The synthetic VFS and MockSink have no real file or network access.

## Threats and controls (TRD §7) and their status in this build
| Threat | Control | Status |
|---|---|---|
| Edit a contract to widen permissions | Ed25519 owner + security signatures; re-verified on content change; v>1 only via approved CR; two-person rule | Implemented and tested |
| Tamper with or rewrite logs | Hash chain; external head anchor detects a full rewrite | Implemented and tested. A local anchor file on the same host is a stand-in for WORM storage: a fully compromised host could rewrite both. |
| Token theft or scope escalation | Signature, revocation list, binding to the issued record, contract-version check, descendant cascade | Implemented and tested |
| Poisoned frozen anchor | Anchor signed; never moved by traffic | Implemented and tested |
| Gateway bypass | Network policy (deployment concern) | Not applicable to the local MVP |
| Malicious payloads | Pydantic validation, 2 MiB body limit (413), path-traversal rejection, `yaml.safe_load` | Implemented and tested |
| Brute-force login / CR spam | In-memory rate limits (20/min login, 10/h CRs per agent) | Implemented and tested (`test_gaps.py`) |
| Detection evasion via probing | Canaries never returned to agents (masked in the API) | Partial: thresholds and decoys are unexposed, but there is no live gateway to probe |

## Known gaps
* **No runtime enforcement.** The Trust Ladder is blocked, so the gateway refuses everything.
* **Demo identities.** Keys in `data/keys/` are generated locally and git-ignored. They are not HSM-backed.
* **CORS** is restricted to the configured origins. TLS is out of scope for local use.
* Dependency scans (`pip-audit`, `npm audit`) were clean on the last run. Rerun them before any release.
