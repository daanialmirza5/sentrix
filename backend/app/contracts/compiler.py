"""Contract Compiler (FR-1): draft a Role Contract from a tool manifest + system prompt.

The draft is never published automatically. Every field carries the evidence it was inferred
from, and anything that would widen authority beyond the manifest is refused with a warning.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .schema import TOOL_RE

DEFAULT_DENY = ["hr/*", "finance/payroll/*", "secrets/*"]
ROLE_DOMAINS = {
    "procurement": (["procurement", "purchase", "supplier", "vendor", "quote", "rfq"], ["procurement/*", "suppliers/*"]),
    "hr": (["employee", "hr ", "human resources", "leave", "onboarding", "payroll query"], ["hr/handbook/*", "hr/policies/*"]),
    "support": (["customer", "ticket", "support", "helpdesk"], ["support/*", "kb/*"]),
    "finance": (["invoice", "ledger", "accounts payable", "reconcil"], ["finance/invoices/*", "finance/ledger/*"]),
    "research": (["research", "market", "catalog"], ["suppliers/*", "public/*"]),
}
# Phrases that ask for broad authority. They are reported, never granted.
OVERREACH = [
    (r"\b(full|unrestricted|admin(istrator)?|root|super ?user)\b.{0,20}\b(access|privileges?|rights)\b", "broad/admin access"),
    (r"\b(any|all)\s+(files?|data|systems?|endpoints?|domains?)\b", "access to any/all data"),
    (r"\bsend\b.{0,30}\b(anywhere|any (url|domain|server))\b", "unrestricted egress"),
    (r"\b(bypass|disable|ignore)\b.{0,20}\b(security|guardrails?|policy|policies|controls?)\b", "bypassing security controls"),
    (r"\b(salary|salaries|payroll|password|secret|credential)s?\b", "sensitive data domain mentioned"),
]
DANGEROUS_TOOLS = {"shell.exec", "http.post", "fs.write", "fs.delete", "iam.grant", "db.drop"}


def _slug_role(text: str) -> str:
    t = text.lower()
    best, score = "general", 0
    for role, (kw, _) in ROLE_DOMAINS.items():
        s = sum(t.count(k) for k in kw)
        if s > score:
            best, score = role, s
    return best


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip(" -*\t") for p in parts if len(p.strip()) > 12]


def compile_contract(manifest: dict, system_prompt: str, agent_id: str, owner: str) -> dict:
    tools_in = manifest.get("tools", [])
    prompt_l = system_prompt.lower()
    inferred: dict[str, list[dict]] = {"allowed_tools": [], "data_domains": [], "egress_allowlist": [],
                                       "anchors": [], "typical_sequences": [], "role": []}
    warnings: list[str] = []

    role = manifest.get("role") or _slug_role(system_prompt + " " + " ".join(t.get("description", "") for t in tools_in))
    inferred["role"].append({"value": role, "evidence": "explicit in manifest" if manifest.get("role")
                             else "keyword match over system prompt and tool descriptions"})

    allowed: list[str] = []
    for t in tools_in:
        name = (t.get("name") or "").strip()
        if not TOOL_RE.match(name):
            warnings.append(f"Tool {name!r} skipped: name is not namespace.action")
            continue
        if name in DANGEROUS_TOOLS and not t.get("justification"):
            warnings.append(f"Tool {name} is high-risk and has no justification in the manifest; NOT included. "
                            "Add it explicitly after review if it is truly required.")
            continue
        allowed.append(name)
        inferred["allowed_tools"].append({"value": name, "evidence": f"manifest tool: {t.get('description', '')[:120]}"})
    for m in re.findall(r"\b([a-z_]+\.[a-z_]+)\b", prompt_l):
        if TOOL_RE.match(m) and m not in allowed and not re.match(r"^[a-z]+\.(com|in|org|net|internal|io)$", m):
            warnings.append(f"Prompt mentions tool {m} which is not in the manifest; NOT granted.")

    allow_domains = list(manifest.get("data_domains", {}).get("allow", []))
    if not allow_domains and role in ROLE_DOMAINS:
        allow_domains = ROLE_DOMAINS[role][1]
        inferred["data_domains"].append({"value": allow_domains, "evidence": f"default domains for role '{role}'"})
    deny = list(dict.fromkeys(DEFAULT_DENY + list(manifest.get("data_domains", {}).get("deny", []))))
    if role == "hr":
        deny = [d for d in deny if d != "hr/*"] + ["hr/salary*", "hr/compensation/*"]
    deny = [d for d in deny if not any(a.split("/")[0] == d.split("/")[0] and a == d for a in allow_domains)]
    inferred["data_domains"].append({"value": deny, "evidence": "organisation default deny-list (sensitive domains)"})

    hosts: list[str] = []
    for t in tools_in:
        for u in t.get("endpoints", []):
            h = urlparse(u if "://" in u else "https://" + u).hostname
            if h and h not in hosts:
                hosts.append(h)
                inferred["egress_allowlist"].append({"value": h, "evidence": f"endpoint of tool {t.get('name')}"})
    for u in re.findall(r"https?://[^\s)\"']+", system_prompt):
        h = urlparse(u).hostname
        if h and h not in hosts:
            warnings.append(f"Prompt references {h}; added to egress allowlist as INFERRED, confirm during review.")
            hosts.append(h)
            inferred["egress_allowlist"].append({"value": h, "evidence": "URL in system prompt (needs confirmation)"})

    anchors: list[str] = []
    for s in _sentences(system_prompt)[:6]:
        if not any(re.search(p, s.lower()) for p, _ in OVERREACH):
            anchors.append(s[:160])
    for t in tools_in:
        if t.get("name") in allowed and t.get("description"):
            anchors.append(t["description"][:160])
    anchors = list(dict.fromkeys(anchors))[:10] or [f"perform {role} tasks"]
    inferred["anchors"] = [{"value": a, "evidence": "system prompt / tool description"} for a in anchors]

    # Typical sequence: order in which allowed tools are first mentioned in the prompt.
    positions = sorted((prompt_l.find(t.split(".")[-1].replace("_", " ")), t) for t in allowed)
    seq = [t for pos, t in positions if pos >= 0]
    if len(seq) >= 2:
        inferred["typical_sequences"].append({"value": seq, "evidence": "order of tool mentions in prompt"})

    for pat, label in OVERREACH:
        m = re.search(pat, prompt_l)
        if m:
            warnings.append(f"Prompt requests {label} (\"{m.group(0)}\"); NOT granted. Contracts never widen "
                            "authority from prompt text.")

    purpose = (manifest.get("purpose") or (_sentences(system_prompt) or [f"{role} agent"])[0])[:300]
    body = {
        "agent_id": agent_id, "owner": owner, "role": role, "purpose": purpose, "version": 1,
        "allowed_tools": allowed or ["noop.read"],
        "data_domains": {"allow": allow_domains, "deny": deny},
        "egress_allowlist": hosts,
        "typical_sequences": [seq] if len(seq) >= 2 else [],
        "limits": {"pr_value_max_inr": 500000 if role == "procurement" else None, "reads_per_min": 60,
                   "bytes_out_per_task": 200000, "max_sensitivity": 0.6},
        "sensitivity_restrictions": {},
        "anchors": anchors,
    }
    if not allowed:
        warnings.append("No usable tools found; draft uses placeholder noop.read and cannot be published as-is.")
    return {"body": body, "inferred": inferred, "warnings": warnings, "requires_human_review": True}
