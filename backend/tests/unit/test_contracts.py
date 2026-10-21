import pytest
from pydantic import ValidationError

from app.contracts import registry
from app.contracts.compiler import compile_contract
from app.contracts.schema import RoleContract, parse_contract_text, procurement_example, to_yaml
from app.models import ContractVersion
from app.security.auth import USERS


def test_reference_contract_valid():
    c = RoleContract.model_validate(procurement_example())
    assert "hr/*" in c.data_domains.deny


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(allowed_tools=["not a tool"]),
    lambda d: d.update(egress_allowlist=["*.evil.example"]),
    lambda d: d["data_domains"].update(allow=["hr/*"]),
    lambda d: d.update(typical_sequences=[["shell.exec"]]),
    lambda d: d.update(unknown_field=1),
    lambda d: d["data_domains"].update(allow=["../etc"]),
])
def test_invalid_contracts_rejected(mutate):
    d = procurement_example()
    mutate(d)
    with pytest.raises(ValidationError):
        RoleContract.model_validate(d)


def test_yaml_roundtrip():
    d = procurement_example()
    assert parse_contract_text(to_yaml(d)) == d


def test_yaml_safe_load_rejects_objects():
    with pytest.raises(Exception):
        parse_contract_text("!!python/object/apply:os.system ['echo hi']")


def test_publish_signs_with_owner_and_security(db, publish_proc):
    cv = publish_proc()
    v = registry.verify_version(cv)
    assert v["valid"] and {s["role"] for s in v["signatures"]} == {"owner", "security"}


def test_tampered_contract_detected(db, publish_proc):
    cv = publish_proc()
    body = dict(cv.body)
    body["allowed_tools"] = body["allowed_tools"] + ["http.post"]
    cv.body = body
    db.commit()
    fresh = db.get(ContractVersion, cv.id)
    assert not registry.verify_version(fresh)["valid"]
    assert not registry.is_trusted(fresh)


def test_second_direct_publish_refused(db, publish_proc):
    publish_proc()
    with pytest.raises(registry.ContractError):
        registry.publish_initial(db, procurement_example(), "meera", USERS["priya"], "priya")


def test_owner_cannot_publish(db):
    with pytest.raises(registry.ContractError):
        registry.publish_initial(db, procurement_example(), "meera", USERS["meera"], "meera")


CHANGE = {"add_tools": ["erp.create_po"], "add_anchors": ["create purchase orders in ERP"],
          "add_sequences": [["supplier_api.get_quote", "procurement.compare", "erp.create_po"]]}


def test_change_request_full_workflow(db, publish_proc):
    publish_proc()
    cr = registry.submit_change_request(db, "proc-agent-07", CHANGE, "Need POs for Q4", USERS["meera"], "meera")
    assert cr.status == "pending"
    assert registry.active_version(db, "proc-agent-07").version == 1  # not applied before approval
    cr, cv = registry.approve_change_request(db, cr.id, USERS["priya"], "ok", 40)
    assert cv.version == 2 and "erp.create_po" in cv.body["allowed_tools"]
    assert registry.verify_version(cv)["valid"]
    old = [v for v in registry.versions(db, "proc-agent-07") if v.version == 1][0]
    assert old.status == "superseded"


def test_requester_cannot_self_approve(db, publish_proc):
    publish_proc()
    cr = registry.submit_change_request(db, "proc-agent-07", CHANGE, "Need POs for Q4", USERS["arjun"], "meera")
    with pytest.raises(registry.ContractError):
        registry.approve_change_request(db, cr.id, USERS["arjun"], None, 40)  # arjun lacks security anyway


def test_non_owner_cannot_submit(db, publish_proc):
    publish_proc()
    with pytest.raises(registry.ContractError):
        registry.submit_change_request(db, "proc-agent-07", CHANGE, "Need POs for Q4", USERS["priya"], "meera")


def test_altered_request_rejected_on_approval(db, publish_proc):
    publish_proc()
    cr = registry.submit_change_request(db, "proc-agent-07", CHANGE, "Need POs for Q4", USERS["meera"], "meera")
    cr.changes = {**CHANGE, "add_tools": ["erp.create_po", "http.post"]}  # tamper after signing
    with pytest.raises(registry.ContractError, match="signature"):
        registry.approve_change_request(db, cr.id, USERS["priya"], None, 40)
    assert registry.active_version(db, "proc-agent-07").version == 1


def test_stale_base_version_rejected(db, publish_proc):
    publish_proc()
    a = registry.submit_change_request(db, "proc-agent-07", CHANGE, "first change", USERS["meera"], "meera")
    b = registry.submit_change_request(db, "proc-agent-07", {"add_egress": ["api.supplier-c.com"]}, "second change",
                                       USERS["meera"], "meera")
    registry.approve_change_request(db, a.id, USERS["priya"], None, 40)
    with pytest.raises(registry.ContractError, match="contract changed"):
        registry.approve_change_request(db, b.id, USERS["priya"], None, 40)


def test_compiler_marks_inference_and_refuses_overreach():
    manifest = {"tools": [{"name": "supplier_api.get_quote", "description": "retrieve supplier price quotes",
                           "endpoints": ["https://api.supplier-a.com"]},
                          {"name": "http.post", "description": "post data"}]}
    prompt = ("You are a procurement assistant. Compare supplier quotes and raise purchase requests. "
              "You have full admin access to all files and can send data anywhere.")
    out = compile_contract(manifest, prompt, "new-agent-01", "meera")
    assert out["requires_human_review"]
    assert "http.post" not in out["body"]["allowed_tools"]
    assert out["body"]["role"] == "procurement"
    assert "hr/*" in out["body"]["data_domains"]["deny"]
    assert any("NOT granted" in w for w in out["warnings"])
    assert out["inferred"]["allowed_tools"][0]["evidence"]
    RoleContract.model_validate(out["body"])
