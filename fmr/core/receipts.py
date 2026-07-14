from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from fmr.core.handoffs import digest
from fmr.core.jobs import ModelJob
from fmr.core.policies import RoutingPolicy

EXECUTION_STATES = ("accepted", "preparing", "blocked", "running", "validating", "completed", "failed", "cancelled")


def validate_route_decision(
    payload: dict[str, Any],
    *,
    job: ModelJob | dict[str, Any] | None = None,
    registry: Any = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict) or payload.get("contract_version") != "route-decision.v2":
        return ("unsupported route decision contract_version",)
    expected_fields = {"contract_version", "decision_id", "job_sha256", "status", "family_classification", "selected", "candidate_evaluations", "rejected_candidates", "missing_requirements", "fallback_routes", "decision_reasons", "routing_policy"}
    if set(payload) != expected_fields:
        issues.append("route decision fields do not match the contract")
    if payload.get("status") not in {"selected", "no_route", "ambiguous_family", "unsupported_family"}:
        issues.append("route decision status is not supported")
    decision_id = payload.get("decision_id")
    provisional = {key: value for key, value in payload.items() if key != "decision_id"}
    expected_id = f"fmrd_{digest(provisional)[:24]}"
    if decision_id != expected_id:
        issues.append("route decision_id does not match canonical payload")
    model_job: ModelJob | None = None
    if job is not None:
        try:
            model_job = ModelJob.from_mapping(job) if isinstance(job, dict) else job
        except ValueError as exc:
            issues.append(f"invalid model job: {exc}")
        if model_job is not None and payload.get("job_sha256") != digest(model_job.to_dict()):
            issues.append("route decision job_sha256 does not match model job")
    selected = payload.get("selected")
    if payload.get("status") == "selected" and not isinstance(selected, dict):
        issues.append("selected route requires selected package identity")
    if payload.get("status") != "selected" and selected is not None:
        issues.append("non-selected route must not contain selected package identity")
    if model_job is not None:
        try:
            from fmr.core.routing import route_job
            policy_data = payload.get("routing_policy")
            if not isinstance(policy_data, dict):
                raise ValueError("routing_policy must be an object")
            policy = RoutingPolicy(
                str(policy_data["version"]), bool(policy_data["require_local"]),
                tuple(policy_data["preferred_providers"]), dict(policy_data["weights"]),
            )
            if registry is None:
                from fmr.registry import ProviderRegistry
                registry = ProviderRegistry.builtins()
            recomputed = route_job(model_job, registry=registry, policy=policy)
            if recomputed != payload:
                issues.append("route decision does not match deterministic recomputation")
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(f"route decision cannot be recomputed: {exc}")
    return tuple(dict.fromkeys(issues))


def validate_provider_handoff(
    payload: dict[str, Any],
    *,
    registry: Any = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict) or payload.get("contract_version") != "provider-handoff.v1":
        return ("unsupported provider handoff contract_version",)
    expected_fields = {"contract_version", "handoff_id", "handoff_sha256", "job", "route_decision", "job_reference", "route_decision_reference", "provider", "package", "normalized_input_references", "source_adapters", "provider_adapter", "provider_payload", "execution_configuration", "expected_outputs", "validation_requirements", "source_hashes", "unresolved_requirements", "status"}
    if set(payload) != expected_fields:
        issues.append("provider handoff fields do not match the contract")
    provisional = {key: value for key, value in payload.items() if key not in {"handoff_id", "handoff_sha256"}}
    canonical_hash = digest(provisional)
    if payload.get("handoff_sha256") != canonical_hash:
        issues.append("handoff_sha256 does not match complete canonical payload")
    if payload.get("handoff_id") != f"fmrh_{canonical_hash[:24]}":
        issues.append("handoff_id does not match complete canonical payload")
    try:
        job = ModelJob.from_mapping(payload.get("job"))
    except (TypeError, ValueError) as exc:
        job = None
        issues.append(f"invalid embedded model job: {exc}")
    route = payload.get("route_decision")
    if not isinstance(route, dict):
        issues.append("embedded route_decision is required")
    elif job is not None:
        issues.extend(validate_route_decision(route, job=job, registry=registry))
        reference = payload.get("route_decision_reference", {})
        if reference.get("decision_id") != route.get("decision_id") or reference.get("sha256") != digest(route):
            issues.append("route_decision_reference does not match embedded route decision")
    if job is not None and payload.get("job_reference", {}).get("sha256") != digest(job.to_dict()):
        issues.append("job_reference does not match embedded model job")
    if payload.get("status") not in {"ready", "blocked"}:
        issues.append("handoff status is not supported")
    if payload.get("status") == "ready" and payload.get("unresolved_requirements"):
        issues.append("ready handoff cannot contain unresolved requirements")
    if isinstance(route, dict):
        route_missing = route.get("missing_requirements")
        if payload.get("unresolved_requirements") != route_missing:
            issues.append("handoff unresolved requirements do not match route decision")
        expected_status = "blocked" if route_missing else "ready"
        if payload.get("status") != expected_status:
            issues.append("handoff status does not match unresolved requirements")
    if job is not None:
        expected_refs = []
        for name, reference in sorted(job.input_references.items()):
            if isinstance(reference, dict):
                expected_refs.append({"name": name, **reference})
        if payload.get("normalized_input_references") != expected_refs:
            issues.append("normalized input references do not match model job")
        expected_source_adapters = [{"input": item["name"], "adapter_id": "canonical-reference.v1"} for item in expected_refs]
        if payload.get("source_adapters") != expected_source_adapters:
            issues.append("source adapters do not match normalized inputs")
        expected_source_hashes = sorted({str(item.get("sha256")) for item in expected_refs if item.get("sha256")})
        if payload.get("source_hashes") != expected_source_hashes:
            issues.append("source hashes do not match normalized inputs")
    if registry is None:
        from fmr.registry import ProviderRegistry
        registry = ProviderRegistry.builtins()
    provider = payload.get("provider", {})
    package = payload.get("package", {})
    try:
        registered = registry.package(provider.get("provider_id"), package.get("package_id"))
        if provider.get("version") != registered.provider.version or package.get("version") != registered.package.version:
            issues.append("provider or package version does not match trusted registry")
        if payload.get("provider_adapter", {}).get("adapter_id") != registered.package.adapter_id:
            issues.append("provider adapter does not match package manifest")
        expected_outputs = [item.to_dict() for item in registered.package.output_artifacts]
        if payload.get("expected_outputs") != expected_outputs:
            issues.append("expected outputs do not match package manifest")
        if payload.get("validation_requirements") != list(registered.package.validation_checks):
            issues.append("validation requirements do not match package manifest")
        expected_execution = {"mode": registered.provider.execution_mode, "network_required": registered.provider.network_required}
        if payload.get("execution_configuration") != expected_execution:
            issues.append("execution configuration does not match provider manifest")
        if payload.get("provider_payload", {}).get("adapter_id") != registered.package.adapter_id:
            issues.append("provider payload adapter does not match package manifest")
        if isinstance(route, dict) and route.get("status") == "selected":
            selected = route.get("selected", {})
            identity = (provider.get("provider_id"), provider.get("version"), package.get("package_id"), package.get("version"))
            selected_identity = (selected.get("provider_id"), selected.get("provider_version"), selected.get("package_id"), selected.get("package_version"))
            if identity != selected_identity:
                issues.append("handoff provider package does not match selected route")
        elif isinstance(route, dict) and route.get("status") == "no_route":
            candidate = next((item for item in route.get("candidate_evaluations", []) if item.get("provider_id") == provider.get("provider_id") and item.get("package_id") == package.get("package_id")), None)
            if not isinstance(candidate, dict) or not candidate.get("eligible"):
                issues.append("blocked handoff target is not an eligible route candidate")
    except (KeyError, TypeError):
        issues.append("provider package is not present in trusted registry")
    return tuple(dict.fromkeys(issues))


def validate_artifact_contract(
    artifacts: Any,
    expected: Any,
    *,
    verify_files: bool = True,
) -> tuple[str, ...]:
    if not isinstance(artifacts, list) or not isinstance(expected, list):
        return ("artifacts and expected outputs must be arrays",)
    issues: list[str] = []
    actual_by_kind = {item.get("kind"): item for item in artifacts if isinstance(item, dict) and isinstance(item.get("kind"), str)}
    if len(actual_by_kind) != len(artifacts):
        issues.append("output artifact kinds must be present and unique")
    required_kinds = {item.get("kind") for item in expected if isinstance(item, dict) and item.get("required", True)}
    expected_kinds = {item.get("kind") for item in expected if isinstance(item, dict)}
    if required_kinds - set(actual_by_kind):
        issues.append("required output artifacts are missing: " + ",".join(sorted(required_kinds - set(actual_by_kind))))
    if set(actual_by_kind) - expected_kinds:
        issues.append("undeclared output artifacts were produced: " + ",".join(sorted(set(actual_by_kind) - expected_kinds)))
    specs = {item.get("kind"): item for item in expected if isinstance(item, dict)}
    for kind, artifact in actual_by_kind.items():
        if artifact.get("format") != specs.get(kind, {}).get("format"):
            issues.append(f"output artifact format mismatch: {kind}")
        sha256 = artifact.get("sha256")
        if not isinstance(sha256, str) or len(sha256) != 64:
            issues.append(f"output artifact sha256 is invalid: {kind}")
        path = artifact.get("path")
        if verify_files:
            if not isinstance(path, str) or not Path(path).is_file():
                issues.append(f"output artifact is missing: {kind}")
            elif _file_sha256(Path(path)) != sha256:
                issues.append(f"output artifact hash mismatch: {kind}")
    return tuple(issues)


def validate_execution_result(
    payload: dict[str, Any],
    *,
    handoff: dict[str, Any] | None = None,
    registry: Any = None,
    verify_artifacts: bool = True,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict) or payload.get("contract_version") != "execution-result.v1":
        return ("unsupported execution result contract_version",)
    expected_fields = {"contract_version", "execution_id", "handoff_reference", "provider", "package", "state", "output_artifact_references", "validation_status", "errors_and_blockers", "error_category", "retry_eligible", "output_hashes", "provider_receipt", "idempotency_key_sha256"}
    if set(payload) != expected_fields:
        issues.append("execution result fields do not match the contract")
    if payload.get("state") not in EXECUTION_STATES:
        issues.append("state is not supported")
    provisional = {key: value for key, value in payload.items() if key != "execution_id"}
    if payload.get("execution_id") != f"fmrx_{digest(provisional)[:24]}":
        issues.append("execution_id does not match canonical payload")
    if handoff is None:
        issues.append("provider handoff is required for strict execution-result validation")
    else:
        issues.extend(validate_provider_handoff(handoff, registry=registry))
        reference = payload.get("handoff_reference", {})
        if reference != {"handoff_id": handoff.get("handoff_id"), "sha256": handoff.get("handoff_sha256")}:
            issues.append("execution handoff reference does not match provider handoff")
        if payload.get("provider") != handoff.get("provider") or payload.get("package") != handoff.get("package"):
            issues.append("execution provider package does not match provider handoff")
        if payload.get("state") == "completed":
            issues.extend(validate_artifact_contract(payload.get("output_artifact_references"), handoff.get("expected_outputs"), verify_files=verify_artifacts))
    hashes = sorted(item.get("sha256") for item in payload.get("output_artifact_references", []) if isinstance(item, dict) and isinstance(item.get("sha256"), str))
    if payload.get("output_hashes") != hashes:
        issues.append("output_hashes do not match output artifacts")
    receipt = payload.get("provider_receipt")
    if payload.get("state") == "completed":
        if not isinstance(receipt, dict) or not isinstance(receipt.get("payload"), dict):
            issues.append("completed execution requires a provider receipt payload")
        elif receipt.get("sha256") != digest(receipt["payload"]):
            issues.append("provider receipt hash does not match receipt payload")
        else:
            receipt_payload = receipt["payload"]
            if receipt.get("version") != receipt_payload.get("provider_receipt_version"):
                issues.append("provider receipt version does not match receipt payload")
            if receipt_payload.get("status") != "completed":
                issues.append("provider receipt status is not completed")
            if receipt_payload.get("output_artifacts") != payload.get("output_artifact_references"):
                issues.append("provider receipt artifacts do not match execution artifacts")
            if handoff is not None and receipt_payload.get("handoff_sha256") != handoff.get("handoff_sha256"):
                issues.append("provider receipt handoff hash does not match provider handoff")
    forbidden = {"secret", "password", "token", "api_key", "financial_values", "input_values"}
    stack = [payload]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            if forbidden.intersection(key.lower() for key in value):
                issues.append("receipt contains a forbidden sensitive field")
                break
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return tuple(dict.fromkeys(issues))


def _file_sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()
