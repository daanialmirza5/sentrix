"""Seed the demo database with the PRD fleet (synthetic agents, signed contracts, one change request).

Usage (backend running on :8000):  backend\\.venv\\Scripts\\python.exe scripts\\seed_demo.py
Talks to the API over HTTP, so every write goes through the same auth and validation as the UI.
Idempotent: existing agents/contracts are skipped.
"""
from __future__ import annotations

import os
import sys

import httpx

BASE = os.environ.get("SENTRIX_API", "http://127.0.0.1:8000")
PW = os.environ.get("SENTRIX_DEMO_PASSWORD", "sentrix-demo")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.contracts.schema import procurement_example  # noqa: E402

FLEET = [
    ("proc-agent-07", "Procurement-Agent-07", "meera", "procurement"),
    ("proc-agent-03", "Procurement-Agent-03", "meera", "procurement"),
    ("orchestrator-01", "Orchestrator-01", "arjun", "orchestrator"),
    ("support-agent-05", "Support-Agent-05", "arjun", "support"),
]


def contract_for(agent_id: str, owner: str, role: str) -> dict:
    if role == "procurement":
        return procurement_example(agent_id, owner)
    if role == "support":
        return {"agent_id": agent_id, "owner": owner, "role": "support",
                "purpose": "Answer customer tickets using the knowledge base", "allowed_tools": ["kb.search", "ticket.reply"],
                "data_domains": {"allow": ["support/*"], "deny": ["hr/*", "finance/payroll/*", "secrets/*"]},
                "egress_allowlist": [], "typical_sequences": [["kb.search", "ticket.reply"]],
                "anchors": ["search the support knowledge base", "reply to customer tickets"]}
    return {"agent_id": agent_id, "owner": owner, "role": role, "purpose": "Plan tasks and delegate to role agents",
            "allowed_tools": ["agent.message", "agent.inbox", "supplier_api.get_quote", "procurement.compare", "kb.search"],
            "data_domains": {"allow": ["procurement/*", "suppliers/*", "support/*"],
                             "deny": ["hr/*", "finance/payroll/*", "secrets/*"]},
            "egress_allowlist": [], "anchors": ["delegate procurement and support tasks to agents"]}


def login(c: httpx.Client, user: str) -> dict:
    r = c.post("/v1/auth/login", json={"username": user, "password": PW})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=30) as c:
        arjun, priya, meera = login(c, "arjun"), login(c, "priya"), login(c, "meera")
        for aid, name, owner, role in FLEET:
            r = c.post("/v1/agents", headers=arjun, json={"agent_id": aid, "name": name, "owner": owner, "role": role})
            print("register", aid, r.status_code)
            r = c.post(f"/v1/contracts/{aid}/versions", headers=priya,
                       json={"contract": contract_for(aid, owner, role), "reviewed": True})
            print("publish ", aid, r.status_code, r.json().get("detail", ""))
        crs = c.get("/v1/change-requests", headers=meera).json()
        if not any(cr["agent_id"] == "proc-agent-07" for cr in crs):
            r = c.post("/v1/change-requests", headers=meera, json={
                "agent_id": "proc-agent-07", "justification": "Procurement must raise purchase orders from Q4 (Flow B).",
                "changes": {"add_tools": ["erp.create_po"], "add_anchors": ["create purchase orders in ERP"],
                            "add_sequences": [["supplier_api.get_quote", "procurement.compare", "erp.create_po"]]}})
            print("change request", r.status_code, r.json().get("id"))
        print("audit", c.get("/v1/audit/verify", headers=priya).json())


if __name__ == "__main__":
    main()
