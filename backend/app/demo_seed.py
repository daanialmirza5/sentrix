"""Synthetic demo fleet (PRD personas and agents). Used by scripts/seed_demo.py and, when
SENTRIX_AUTO_SEED=1, on startup of an empty database (cloud deployments have no seed step)."""
from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from .audit import chain
from .contracts import registry
from .contracts.schema import procurement_example
from .engines.deception import canary_for
from .models import Agent
from .security import keys
from .security.auth import USERS

FLEET = [
    ("proc-agent-07", "Procurement-Agent-07", "meera", "procurement"),
    ("proc-agent-03", "Procurement-Agent-03", "meera", "procurement"),
    ("orchestrator-01", "Orchestrator-01", "arjun", "orchestrator"),
    ("support-agent-05", "Support-Agent-05", "arjun", "support"),
]

PO_CHANGE = {"add_tools": ["erp.create_po"], "add_anchors": ["create purchase orders in ERP"],
             "add_sequences": [["supplier_api.get_quote", "procurement.compare", "erp.create_po"]]}
PO_JUSTIFICATION = "Procurement must raise purchase orders from Q4 (Flow B)."


def contract_for(agent_id: str, owner: str, role: str) -> dict:
    if role == "procurement":
        return procurement_example(agent_id, owner)
    deny = ["hr/*", "finance/payroll/*", "secrets/*"]
    if role == "support":
        return {"agent_id": agent_id, "owner": owner, "role": "support",
                "purpose": "Answer customer tickets using the knowledge base", "allowed_tools": ["kb.search", "ticket.reply"],
                "data_domains": {"allow": ["support/*"], "deny": deny}, "egress_allowlist": [],
                "typical_sequences": [["kb.search", "ticket.reply"]],
                "anchors": ["search the support knowledge base", "reply to customer tickets"]}
    return {"agent_id": agent_id, "owner": owner, "role": role, "purpose": "Plan tasks and delegate to role agents",
            "allowed_tools": ["agent.message", "agent.inbox", "supplier_api.get_quote", "procurement.compare", "kb.search"],
            "data_domains": {"allow": ["procurement/*", "suppliers/*", "support/*"], "deny": deny},
            "egress_allowlist": [], "anchors": ["delegate procurement and support tasks to agents"]}


def seed_if_empty(db: Session) -> bool:
    """Create the fleet, signed v1 contracts and one pending change request. No-op if agents exist."""
    if db.query(Agent).first() is not None:
        return False
    for aid, name, owner, role in FLEET:
        db.add(Agent(id=aid, name=name, owner=owner, role=role, kind="simulated",
                     secret_hash=keys.sha256_hex(secrets.token_urlsafe(24)), canary=canary_for(aid)))
        chain.append(db, "admin", agent_id=aid, actor="arjun", verdict="agent_registered", details={"owner": owner, "role": role})
        db.flush()
        registry.publish_initial(db, contract_for(aid, owner, role), owner, USERS["priya"], "priya")
    registry.submit_change_request(db, "proc-agent-07", PO_CHANGE, PO_JUSTIFICATION, USERS["meera"], "meera")
    return True
