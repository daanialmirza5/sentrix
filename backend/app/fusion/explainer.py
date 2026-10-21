"""Deterministic, template-based alert explanations (no LLM; reproducible and auditable)."""
from __future__ import annotations

from .risk import NAMES, Fused

LEVEL_NAMES = {0: "L0 Allow", 1: "L1 Watch + step-up", 2: "L2 Restrict", 3: "L3 Sandbox", 4: "L4 Isolate"}


def factor_line(f: Fused) -> str:
    parts = [f"{NAMES[k]} {v:.0f}%" for k, v in sorted(f.contributions.items(), key=lambda kv: -kv[1]) if v > 0]
    line = " | ".join(parts) if parts else "no weighted signal"
    if f.override == "deception":
        line = f"Deception override: risk floored at 95 (background factors: {line})"
    elif f.override == "drift":
        line = f"Drift override from CUSUM alarm (background factors: {line})"
    return line + " | Behavior: disabled (not implemented)"


def why(action: dict, rolefit: dict, prov: dict, dec: dict) -> str:
    bits = [f"{action['verb']} {action['resource'] or action['tool']}"]
    if rolefit.get("rules"):
        bits.append("; ".join(r["detail"] for r in rolefit["rules"][:3]))
    elif rolefit.get("fit") is not None:
        bits.append(f"semantic fit {rolefit['fit']:.2f} to '{rolefit.get('nearest_anchor')}'")
    if prov.get("window_id"):
        bits.append(f"{prov['steps_since']} step(s) after ingesting UNTRUSTED {prov['source']}")
    if dec.get("honey"):
        bits.append(f"touched honey-resource {dec['honey']}")
    if dec.get("canaries"):
        bits.append("canary value in outbound payload: " + ", ".join(c["masked"] for c in dec["canaries"]))
    return ". ".join(bits) + "."


def cause_line(attribution: dict | None) -> str | None:
    if not attribution:
        return None
    span = attribution.get("span")
    if not span:
        return f"{attribution['source']} (content no longer retained; hash {attribution['content_hash'][:19]}…)"
    q = "uncertain" if attribution.get("uncertain") else f"confidence {attribution['confidence']:.2f}"
    return f"{attribution['source']}, page {span['page']}, line {span['line']} (\"{span['text'][:80]}\") [{q}]"


def recommendations(level: int, verdict: str, dec: dict) -> list[str]:
    recs = []
    if dec.get("honey") or dec.get("canaries"):
        recs.append("Treat as confirmed compromise: review the causal source and rotate any credentials it could reach.")
    if level >= 4:
        recs += ["Keep the session quarantined until security review completes.",
                 "Release only after the cause (source document / chain parent) is removed."]
    elif level == 3:
        recs.append("Inspect recorded intent from the sandbox before deciding to release or isolate.")
    elif level == 2:
        recs.append("Owner should acknowledge; restriction lifts after 5 clean windows.")
    elif level == 1:
        recs.append("Approve or deny pending step-up requests.")
    if verdict == "deny":
        recs.append("No side effects occurred for the denied action.")
    return recs
