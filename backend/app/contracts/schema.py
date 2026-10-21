"""Role Contract schema (TRD 3.1). Contracts are JSON or YAML; signatures are detached."""
from __future__ import annotations

import fnmatch
import re
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TOOL_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$")


class DataDomains(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)

    @field_validator("allow", "deny")
    @classmethod
    def _globs(cls, v: list[str]) -> list[str]:
        out = []
        for g in v:
            g = g.strip().lstrip("/")
            if not g or ".." in g:
                raise ValueError(f"invalid domain glob {g!r}")
            out.append(g)
        return out


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pr_value_max_inr: int | None = 500000
    reads_per_min: int = 60
    bytes_out_per_task: int = 200000
    max_sensitivity: float = Field(default=0.6, ge=0, le=1)


class RoleContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    owner: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=2, max_length=80)
    purpose: str = Field(min_length=5, max_length=500)
    version: int = Field(default=1, ge=1)
    allowed_tools: list[str] = Field(min_length=1)
    data_domains: DataDomains = Field(default_factory=DataDomains)
    egress_allowlist: list[str] = Field(default_factory=list)
    typical_sequences: list[list[str]] = Field(default_factory=list)
    limits: Limits = Field(default_factory=Limits)
    sensitivity_restrictions: dict[str, float] = Field(default_factory=dict)
    anchors: list[str] = Field(min_length=1)
    created_at: str | None = None
    updated_at: str | None = None
    approval_history: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("allowed_tools")
    @classmethod
    def _tools(cls, v: list[str]) -> list[str]:
        for t in v:
            if not TOOL_RE.match(t):
                raise ValueError(f"invalid tool name {t!r} (expected namespace.action)")
        if len(set(v)) != len(v):
            raise ValueError("duplicate tool in allowed_tools")
        return v

    @field_validator("egress_allowlist")
    @classmethod
    def _hosts(cls, v: list[str]) -> list[str]:
        for h in v:
            if "*" in h or not HOST_RE.match(h.lower()):
                raise ValueError(f"egress host {h!r} must be an exact hostname (no wildcards)")
        return [h.lower() for h in v]

    @model_validator(mode="after")
    def _consistency(self):
        for seq in self.typical_sequences:
            for step in seq:
                if "." in step and step not in self.allowed_tools:
                    raise ValueError(f"typical sequence step {step!r} is not an allowed tool")
        overlap = [a for a in self.data_domains.allow for d in self.data_domains.deny
                   if fnmatch.fnmatch(a.rstrip("*").rstrip("/") + "/x", d)]
        if overlap:
            raise ValueError(f"allowed domains overlap denied domains: {overlap}")
        return self

    def signable(self) -> dict:
        """The exact payload that owner + security signatures cover."""
        return self.model_dump(mode="json", exclude={"approval_history"})


def parse_contract_text(text: str, fmt: str = "auto") -> dict:
    """Parse JSON or YAML. yaml.safe_load is used so no arbitrary object construction."""
    if fmt not in {"auto", "json", "yaml"}:
        raise ValueError("format must be json, yaml or auto")
    data = yaml.safe_load(text)  # YAML is a superset of JSON
    if not isinstance(data, dict):
        raise ValueError("contract must be a mapping")
    data.pop("signature", None)
    data.pop("signatures", None)
    return data


def to_yaml(contract: dict) -> str:
    return yaml.safe_dump(contract, sort_keys=False, allow_unicode=True)


def procurement_example(agent_id: str = "proc-agent-07", owner: str = "meera") -> dict:
    """The TRD 3.1 reference contract, extended with fs.read for procurement documents."""
    return {
        "agent_id": agent_id,
        "owner": owner,
        "role": "procurement",
        "purpose": "Compare supplier prices and raise purchase requests under INR 5,00,000",
        "version": 1,
        "allowed_tools": ["supplier_api.get_quote", "procurement.compare", "erp.create_pr", "web.fetch", "fs.read"],
        "data_domains": {"allow": ["procurement/*", "suppliers/*"], "deny": ["hr/*", "finance/payroll/*", "secrets/*"]},
        "egress_allowlist": ["api.supplier-a.com", "api.supplier-b.com", "erp.internal"],
        "typical_sequences": [
            ["supplier_api.get_quote", "procurement.compare", "erp.create_pr"],
            ["supplier_api.get_quote", "web.fetch", "procurement.compare", "erp.create_pr"],
            ["fs.read", "supplier_api.get_quote", "procurement.compare"],
        ],
        "limits": {"pr_value_max_inr": 500000, "reads_per_min": 60, "bytes_out_per_task": 200000, "max_sensitivity": 0.6},
        "sensitivity_restrictions": {"suppliers/*/bank_details*": 0.5},
        "anchors": [
            "retrieve supplier price quotes",
            "compare supplier quotes and prices",
            "create purchase requests in ERP",
            "read procurement documents and supplier catalogues",
            "fetch supplier quote documents from supplier portal",
        ],
    }
