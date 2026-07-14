from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RoutingPolicy:
    version: str
    require_local: bool
    preferred_providers: tuple[str, ...]
    weights: dict[str, int]
    organization_id: str | None = None
    allowed_providers: tuple[str, ...] = ()
    approved_provider_versions: tuple[str, ...] = ()
    approved_package_versions: tuple[str, ...] = ()
    prohibited_execution_modes: tuple[str, ...] = ()
    approved_template_ids: tuple[str, ...] = ()
    require_approved_template: bool = False
    audit_retention_days: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "require_local": self.require_local,
            "preferred_providers": list(self.preferred_providers),
            "weights": dict(sorted(self.weights.items())),
            "organization_id": self.organization_id,
            "allowed_providers": list(self.allowed_providers),
            "approved_provider_versions": list(self.approved_provider_versions),
            "approved_package_versions": list(self.approved_package_versions),
            "prohibited_execution_modes": list(self.prohibited_execution_modes),
            "approved_template_ids": list(self.approved_template_ids),
            "require_approved_template": self.require_approved_template,
            "audit_retention_days": self.audit_retention_days,
        }


_WEIGHTS = {
    "exact_family_match": 100,
    "industry_match": 20,
    "deliverable_coverage": 20,
    "data_readiness": 30,
    "preferred_output_format": 15,
    "local_execution": 5,
    "execution_mode_preference": 15,
    "determinism": 10,
    "provider_preference": 25,
    "validation_strength": 10,
}

DEFAULT_POLICY = RoutingPolicy("default.v2", False, ("python-forecast", "native-xlsx", "reference-handoff"), dict(_WEIGHTS))
LOCAL_ONLY_POLICY = RoutingPolicy("local-only.v2", True, ("native-xlsx", "python-forecast"), dict(_WEIGHTS))
JSON_FIRST_POLICY = RoutingPolicy("json-first.v1", False, ("python-forecast", "native-xlsx"), dict(_WEIGHTS))
SPREADSHEET_FIRST_POLICY = RoutingPolicy("spreadsheet-first.v1", False, ("native-xlsx", "python-forecast"), dict(_WEIGHTS))


def routing_policy(name: str | None = None) -> RoutingPolicy:
    if name in (None, "default", "default.v2"):
        return DEFAULT_POLICY
    if name in ("local-only", "local-only.v2"):
        return LOCAL_ONLY_POLICY
    if name in ("json-first", "json-first.v1"):
        return JSON_FIRST_POLICY
    if name in ("spreadsheet-first", "spreadsheet-first.v1"):
        return SPREADSHEET_FIRST_POLICY
    raise ValueError(f"unknown routing policy: {name}")
