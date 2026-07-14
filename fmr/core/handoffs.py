from __future__ import annotations

import hashlib
import json
from typing import Any

from fmr.core.jobs import ModelJob
from fmr.registry import RegisteredPackage


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _reject_embedded_secrets(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.lower().replace("-", "_")
            if normalized in {"secret", "secrets", "password", "token", "api_key", "access_token"}:
                raise ValueError(f"secrets must be supplied by reference, not embedded at {path}.{key}")
            _reject_embedded_secrets(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_embedded_secrets(item, f"{path}[{index}]")


def compile_provider_handoff(
    job: ModelJob,
    decision: dict[str, Any],
    registered: RegisteredPackage,
    provider_payload: dict[str, Any],
) -> dict[str, Any]:
    selected = decision.get("selected")
    if decision.get("contract_version") != "route-decision.v2" or decision.get("status") not in {"selected", "no_route"}:
        raise ValueError("a selected or readiness-blocked route-decision.v2 is required")
    expected = (registered.provider.provider_id, registered.package.package_id)
    if decision.get("status") == "selected":
        if not isinstance(selected, dict) or (selected.get("provider_id"), selected.get("package_id")) != expected:
            raise ValueError("registered package does not match the route decision")
    else:
        eligible = {(item.get("provider_id"), item.get("package_id")) for item in decision.get("candidate_evaluations", []) if item.get("eligible")}
        if expected not in eligible:
            raise ValueError("blocked handoff target must be an eligible route candidate")
    if decision.get("job_sha256") != digest(job.to_dict()):
        raise ValueError("route decision does not match the model job")
    _reject_embedded_secrets(provider_payload)
    unresolved = tuple(decision.get("missing_requirements", ()))
    normalized_refs = []
    for name, reference in sorted(job.input_references.items()):
        if not isinstance(reference, dict):
            raise ValueError(f"input_references.{name} must be an object")
        normalized_refs.append({"name": name, **reference})
    _reject_embedded_secrets(normalized_refs, "normalized_input_references")
    provisional = {
        "contract_version": "provider-handoff.v1",
        "job_reference": {"sha256": digest(job.to_dict())},
        "route_decision_reference": {"decision_id": decision["decision_id"], "sha256": digest(decision)},
        "provider": {"provider_id": registered.provider.provider_id, "version": registered.provider.version},
        "package": {"package_id": registered.package.package_id, "version": registered.package.version},
        "normalized_input_references": normalized_refs,
        "source_adapters": [{"input": item["name"], "adapter_id": "canonical-reference.v1"} for item in normalized_refs],
        "provider_adapter": {"adapter_id": provider_payload.get("adapter_id")},
        "provider_payload": provider_payload,
        "execution_configuration": {"mode": registered.provider.execution_mode, "network_required": registered.provider.network_required},
        "expected_outputs": list(registered.package.output_artifacts),
        "validation_requirements": list(registered.package.validation_checks),
        "source_hashes": sorted({str(item.get("sha256")) for item in normalized_refs if item.get("sha256")}),
        "unresolved_requirements": list(unresolved),
        "status": "blocked" if unresolved else "ready",
    }
    return {**provisional, "handoff_id": f"fmrh_{digest(provisional)[:24]}", "handoff_sha256": digest(provisional)}
