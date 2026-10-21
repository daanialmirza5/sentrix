import ast
import math
from pathlib import Path

import numpy as np
import pytest

from app.config import settings
from app.contracts.schema import RoleContract, procurement_example
from app.engines import behavior, canary, deception, drift, provenance, rolefit
from app.engines.embeddings import embedder
from app.fusion.risk import fuse
from app.gateway import tools
from app.models import Agent

C = RoleContract.model_validate(procurement_example())


def act(tool, **args):
    return tools.describe(tool, args)


# ---------------------------------------------------------------- tools / sandbox safety
@pytest.mark.parametrize("p", ["../etc/passwd", "hr/../../x", "C:\\Windows", "a\x00b", "", "  ", 5])
def test_path_traversal_blocked(p):
    with pytest.raises(tools.ToolError):
        tools.normalize_path(p)


def test_tools_module_has_no_network_or_file_io():
    src = Path(tools.__file__).read_text()
    tree = ast.parse(src)
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                for a in (n.names if isinstance(n, ast.Import) else [ast.alias(n.module or "")])}
    assert not imported & {"socket", "requests", "httpx", "urllib3", "http", "aiohttp", "subprocess", "os", "shutil"}
    assert "open(" not in src


def test_http_post_goes_to_mock_sink_only():
    a = act("http.post", url=f"https://{tools.MOCK_EXTERNAL_HOST}/upload", body="hello")
    res, trust = tools.execute(a, {}, "agent-x")
    assert tools.SINK.deliveries[-1]["host"] == tools.MOCK_EXTERNAL_HOST
    assert trust == "untrusted" and res["delivered"]["bytes"] == 5


def test_poisoned_fixture_is_inert_marker():
    assert tools.INJECTION_MARKER_RE.search(tools.POISONED_QUOTE)
    assert "/hr/" not in tools.POISONED_QUOTE and "http" not in tools.POISONED_QUOTE.split("[[")[1]


def test_redaction():
    a = act("fs.read", path="/suppliers/supplier-a/bank_details.json")
    res, _ = tools.execute(a, {"path": a.resource}, "x")
    red = tools.redact(res, ("account_number", "ifsc"))
    assert "[REDACTED]" in red["content"] and "account_number" in red["redacted_fields"]


# ---------------------------------------------------------------- role-fit
def test_embedder_is_minilm_or_labelled_fallback():
    embedder.load()
    assert embedder.mode in {"minilm-onnx", "lexical-fallback"}
    if embedder.mode == "lexical-fallback":
        assert embedder.error


def test_in_role_action_low_score():
    r = rolefit.score(act("supplier_api.get_quote", supplier="supplier-a"), C)
    assert not r.hard_deny and r.s_r < 0.3


def test_deny_domain_is_hard_and_max():
    r = rolefit.score(act("fs.read", path="/hr/salary_backup.xlsx"), C)
    assert "deny_domain" in r.hard_deny and r.s_r == 1.0 and r.out_of_contract


def test_semantic_cannot_override_deny(monkeypatch):
    monkeypatch.setattr(embedder, "similarity", lambda a, b: np.ones(len(b)))  # perfect semantic fit
    r = rolefit.score(act("fs.read", path="/hr/salary_backup.xlsx"), C)
    assert r.s_r == 1.0 and "deny_domain" in r.hard_deny


def test_disallowed_tool_and_egress_and_value_limit():
    r = rolefit.score(act("erp.create_po", amount_inr=1000, item="x"), C)
    assert "tool_not_allowed" in r.hard_deny
    r = rolefit.score(act("http.post", url="https://mock-sink.invalid/u", body="x"), C)
    assert {"tool_not_allowed", "egress_not_allowlisted"} <= set(r.hard_deny)
    r = rolefit.score(act("erp.create_pr", amount_inr=900000, item="x"), C)
    assert "value_limit" in r.hard_deny


def test_cold_start_first_action_scored():
    """No history at all: the contract alone yields a decision-grade score."""
    r = rolefit.score(act("fs.read", path="/finance/payroll/october_run.csv"), C)
    assert r.s_r == 1.0


def test_behavior_stub_disabled():
    assert behavior.score().s_b == 0.0 and behavior.status()["implemented"] is False


# ---------------------------------------------------------------- provenance
def test_taint_decay():
    assert provenance.tau(0) == 1.0
    assert math.isclose(provenance.tau(5), math.exp(-1))


def test_attribution_finds_marker_line(db):
    content, w = provenance.ingest(db, agent_id="a", session_id="s", source="supplier_quote.pdf",
                                   text=tools.POISONED_QUOTE, trust="untrusted", step=1, taint_seq=1)
    res = provenance.score(db, session_id="s", step=2, out_of_contract=True, s_r=1.0)
    assert res.window_id == w.id and math.isclose(res.s_p, round(math.exp(-1 / 5), 4))
    attr = provenance.attribute(db, w.id, "read fs read hr salary backup xlsx")
    assert attr["span"]["page"] == 2 and attr["span"]["line"] == 14 and not attr["uncertain"]


def test_clean_doc_attribution_uncertain(db):
    _, w = provenance.ingest(db, agent_id="a", session_id="s", source="quote_clean.pdf", text=tools.CLEAN_QUOTE_A,
                             trust="untrusted", step=1, taint_seq=2)
    attr = provenance.attribute(db, w.id, "read fs read hr salary backup xlsx")
    assert attr["uncertain"]


def test_trusted_ingest_opens_no_window(db):
    _, w = provenance.ingest(db, agent_id="a", session_id="s2", source="x", text="hello", trust="trusted", step=0,
                             taint_seq=3)
    assert w is None


# ---------------------------------------------------------------- deception
def test_honey_and_canary(db):
    deception.seed_honey(db)
    db.add(Agent(id="proc-agent-07", name="p", owner="meera", role="procurement", secret_hash="x",
                 canary=deception.canary_for("proc-agent-07")))
    db.flush()
    r = deception.inspect(db, act("fs.read", path="/hr/salary_backup.xlsx"))
    assert r.d and r.honey == "hr/salary_backup.xlsx"
    r = deception.inspect(db, act("http.get", url="http://internal-api.local/export-all"))
    assert r.d
    decoy = deception.decoy_content("salary_sheet", "proc-agent-07")
    assert deception.DECOY_MARK in decoy and "Test Person" in decoy
    r = deception.inspect(db, act("http.post", url="https://api.supplier-a.com/x", body=decoy))
    assert r.d and r.canaries[0]["owner"] == "proc-agent-07" and "decoy_marker" in r.dlp
    assert r.canaries[0]["masked"].endswith("…")
    assert not deception.inspect(db, act("supplier_api.get_quote", supplier="supplier-a")).d


def test_canaries_unique_per_agent():
    assert deception.canary_for("a") != deception.canary_for("b")
    assert deception.CANARY_RE.fullmatch(deception.canary_for("a"))


# ---------------------------------------------------------------- drift
def _feat(rng, drift_p=0.0):
    if rng.random() < drift_p:
        return drift.action_features("fs.read", C.allowed_tools, False, 0.15, 0.5, False,
                                     f"/suppliers/supplier-{rng.integers(6)}/bank_details.json", 0)
    tool = rng.choice(["supplier_api.get_quote", "procurement.compare", "erp.create_pr", "web.fetch"])
    return drift.action_features(str(tool), C.allowed_tools, False, 0.05, 0.15, tool == "web.fetch",
                                 f"r{rng.integers(30)}", 200 if tool == "erp.create_pr" else 0)


def test_cusum_frozen_anchor_properties(db):
    """Comparative frozen-vs-rolling timing is measured in scripts/eval_drift.py, not asserted here."""
    rng = np.random.default_rng(7)
    for _ in range(20 * 10):
        drift.observe(db, "a", _feat(rng), C.allowed_tools, 1, clean=True)
    st = drift.get_state(db, "a")
    assert st.status == "frozen" and drift.anchor_valid(st)
    mu0 = list(st.anchor["mu"])
    for w in range(60):  # slow drift: share of bank_details reads rises 0 -> 0.59
        for _ in range(10):
            drift.observe(db, "a", _feat(rng, 0.01 * w), C.allowed_tools, 1, clean=True)
    assert st.anchor["mu"] == mu0, "observed traffic must never move the frozen anchor"
    assert st.rolling_mu != mu0, "rolling baseline follows traffic (the weakness the anchor avoids)"
    assert st.alarm and st.cusum > settings.cusum_h
    assert drift.drift_term(db, "a", in_probation=False) >= 0.55
    assert drift.drift_term(db, "a", in_probation=True) == 0.0


def test_tampered_anchor_detected(db):
    rng = np.random.default_rng(1)
    for _ in range(210):
        drift.observe(db, "b", _feat(rng), C.allowed_tools, 1, clean=True)
    st = drift.get_state(db, "b")
    st.anchor = {**st.anchor, "mu": [0.0] * len(st.anchor["mu"])}
    assert not drift.anchor_valid(st)


# ---------------------------------------------------------------- canary heartbeat
def test_isi(db):
    for i in range(10):
        canary.record(db, "inj", "s", "BLUEFINCH-0001", obeyed=i < 8)
        canary.record(db, "res", "s", "BLUEFINCH-0002", obeyed=False)
    hi, lo = canary.isi(db, "inj"), canary.isi(db, "res")
    assert hi["isi"] == round(9 / 12, 4) and lo["isi"] == round(1 / 12, 4)
    assert canary.tightened_defaults(hi["isi"])["step_up_threshold"] == 20
    assert canary.tightened_defaults(lo["isi"]) == {}
    assert tools.HEARTBEAT_MARKER_RE.search(canary.heartbeat_document("BLUEFINCH-AB12"))


# ---------------------------------------------------------------- fusion
def test_fusion_noisy_or_and_contributions():
    f = fuse({"R": 0.97, "P": 0.9, "S": 1.0})
    expected = 1 - (1 - 0.55 * 0.97) * (1 - 0.6 * 0.9) * (1 - 0.6)
    assert math.isclose(f.risk_raw, round(100 * expected, 1))
    assert math.isclose(sum(f.contributions.values()), 100.0, abs_tol=0.05)
    assert f.contributions["B"] == 0.0 and "B" in f.disabled


def test_fusion_zero_and_bounds():
    f = fuse({})
    assert f.risk == 0 and all(v == 0 for v in f.contributions.values())
    f = fuse({"R": 5, "B": -3, "P": 1, "S": 1})
    assert 0 <= f.risk <= 100


def test_fusion_overrides():
    assert fuse({"R": 0.1}, deception=True).risk == 95.0
    assert fuse({"R": 0.1}, deception=True).override == "deception"
    f = fuse({"R": 0.1}, drift_term=0.6)
    assert f.risk == 60.0 and f.override == "drift"
