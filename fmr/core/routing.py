from __future__ import annotations

import hashlib
import json
from typing import Any

from fmr.core.families import FAMILY_BY_ID, classify_job
from fmr.core.jobs import ModelJob
from fmr.core.policies import DEFAULT_POLICY, RoutingPolicy
from fmr.registry import ProviderRegistry, RegisteredPackage


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _version_pin(provider_id: str, version: str) -> str:
    return f"{provider_id}@{version}"


def _evaluate(job: ModelJob, item: RegisteredPackage, policy: RoutingPolicy) -> dict[str, Any]:
    provider, package = item.provider, item.package
    constraints = job.constraints
    rejected: list[str] = []
    if (constraints.local_only or policy.require_local) and provider.execution_mode != "local":
        rejected.append("local_only_requires_local_provider")
    if (constraints.local_only or policy.require_local) and provider.network_required:
        rejected.append("local_only_forbids_network")
    if not constraints.network_allowed and provider.network_required:
        rejected.append("network_not_allowed")
    if constraints.open_source_only and not provider.open_source:
        rejected.append("open_source_only")
    missing_privacy = sorted(set(job.privacy_constraints) - set(provider.privacy_behavior))
    if missing_privacy:
        rejected.append("privacy_constraint_not_met:" + ",".join(missing_privacy))
    if job.licensing_constraints and provider.license not in job.licensing_constraints:
        rejected.append("license_not_allowed")
    if constraints.allowed_providers and provider.provider_id not in constraints.allowed_providers:
        rejected.append("provider_not_allowed")
    if provider.provider_id in constraints.prohibited_providers:
        rejected.append("provider_prohibited")
    if constraints.pinned_provider_versions and _version_pin(provider.provider_id, provider.version) not in constraints.pinned_provider_versions:
        rejected.append("provider_version_not_pinned")
    provider_version = _version_pin(provider.provider_id, provider.version)
    package_version = f"{package.package_id}@{package.version}"
    if policy.allowed_providers and provider.provider_id not in policy.allowed_providers:
        rejected.append("organization_provider_not_approved")
    if policy.approved_provider_versions and provider_version not in policy.approved_provider_versions:
        rejected.append("organization_provider_version_not_approved")
    if policy.approved_package_versions and package_version not in policy.approved_package_versions:
        rejected.append("organization_package_version_not_approved")
    if provider.execution_mode in policy.prohibited_execution_modes:
        rejected.append("organization_execution_mode_prohibited")
    template_id = job.existing_model.get("template_id") if isinstance(job.existing_model, dict) else None
    if policy.require_approved_template and not isinstance(template_id, str):
        rejected.append("organization_approved_template_required")
    elif isinstance(template_id, str) and policy.approved_template_ids and template_id not in policy.approved_template_ids:
        rejected.append("organization_template_not_approved")
    missing_formats = sorted(set(job.output_formats) - set(package.output_formats))
    if missing_formats:
        rejected.append("output_format_not_supported:" + ",".join(missing_formats))
    missing_deliverables = sorted(set(job.requested_deliverables) - set(package.deliverables))
    if missing_deliverables:
        rejected.append("deliverable_not_supported:" + ",".join(missing_deliverables))
    industry_match = job.industry is None or "*" in package.industries or job.industry in package.industries
    if not industry_match:
        rejected.append("industry_not_supported")
    if not item.runtime_available and provider.execution_mode != "handoff_only":
        rejected.append("runtime_unavailable")

    missing_data = tuple(sorted(set(package.required_data) - set(job.available_data)))
    missing_assumptions = tuple(sorted(set(package.required_assumptions) - set(job.available_assumptions)))
    reference_contracts = {
        reference.get("contract_version")
        for reference in job.input_references.values()
        if isinstance(reference, dict) and isinstance(reference.get("contract_version"), str)
    }
    source_adapter_available = bool(set(package.accepted_inputs).intersection(reference_contracts)) or not package.accepted_inputs
    provider_adapter_available = item.provider_adapter_available
    provider_executor_available = item.provider_executor_available
    readiness = {
        "required_data_available": sorted(set(package.required_data).intersection(job.available_data)),
        "required_data_missing": list(missing_data),
        "assumptions_available": sorted(set(package.required_assumptions).intersection(job.available_assumptions)),
        "assumptions_missing": list(missing_assumptions),
        "source_adapter_available": source_adapter_available,
        "provider_adapter_available": provider_adapter_available,
        "provider_executor_available": provider_executor_available,
        "runtime_available": item.runtime_available,
        "validation_available": bool(package.validation_checks),
    }
    blockers = [f"missing_data:{value}" for value in missing_data]
    blockers += [f"missing_assumption:{value}" for value in missing_assumptions]
    if not source_adapter_available:
        blockers.append("source_adapter_unavailable")
    if not provider_adapter_available:
        blockers.append("provider_adapter_unavailable")
    if not provider_executor_available:
        blockers.append("provider_executor_unavailable")

    preference_points = 0
    if provider.provider_id in policy.preferred_providers:
        preference_points = max(len(policy.preferred_providers) - policy.preferred_providers.index(provider.provider_id), 1)
    factors = {
        "exact_family_match": policy.weights["exact_family_match"],
        "industry_match": policy.weights["industry_match"] * (2 if job.industry is not None and job.industry in package.industries else 1) if industry_match else 0,
        "deliverable_coverage": policy.weights["deliverable_coverage"] if not missing_deliverables else 0,
        "data_readiness": policy.weights["data_readiness"] if not missing_data and not missing_assumptions else 0,
        "preferred_output_format": policy.weights["preferred_output_format"] if not missing_formats else 0,
        "local_execution": policy.weights["local_execution"] if provider.execution_mode == "local" else 0,
        "execution_mode_preference": policy.weights["execution_mode_preference"] if job.preferred_execution_mode == provider.execution_mode else 0,
        "determinism": policy.weights["determinism"] if provider.determinism_level.startswith("deterministic") else 0,
        "provider_preference": policy.weights["provider_preference"] * preference_points,
        "validation_strength": policy.weights["validation_strength"] if package.validation_checks else 0,
    }
    executable = not rejected and not blockers
    return {
        "provider_id": provider.provider_id,
        "provider_version": provider.version,
        "package_id": package.package_id,
        "package_version": package.version,
        "execution_mode": provider.execution_mode,
        "eligible": not rejected,
        "executable": executable,
        "rejection_reasons": rejected,
        "readiness": readiness,
        "blockers": blockers,
        "score": sum(factors.values()),
        "score_factors": factors,
    }


def route_job(job: ModelJob | dict[str, Any], *, registry: ProviderRegistry | None = None, policy: RoutingPolicy = DEFAULT_POLICY) -> dict[str, Any]:
    model_job = ModelJob.from_mapping(job) if isinstance(job, dict) else job
    provider_registry = registry or ProviderRegistry.builtins()
    classification = classify_job(model_job)
    evaluations: list[dict[str, Any]] = []
    selected = None
    status = classification["status"]
    if status == "selected":
        evaluations = [_evaluate(model_job, item, policy) for item in provider_registry.packages(classification["selected_family"])]
        ready = [item for item in evaluations if item["executable"]]
        ready.sort(key=lambda item: (-item["score"], item["provider_id"], item["package_id"], item["provider_version"], item["package_version"]))
        if ready:
            selected = {key: ready[0][key] for key in ("provider_id", "provider_version", "package_id", "package_version", "execution_mode")}
            status = "selected"
        else:
            status = "no_route"
    rejected = [item for item in evaluations if not item["eligible"]]
    fallback = [
        {key: item[key] for key in ("provider_id", "provider_version", "package_id", "package_version", "score")}
        for item in sorted((value for value in evaluations if value["executable"] and (not selected or value["package_id"] != selected["package_id"])), key=lambda value: (-value["score"], value["provider_id"], value["package_id"]))
    ]
    if selected:
        chosen = next(item for item in evaluations if item["provider_id"] == selected["provider_id"] and item["package_id"] == selected["package_id"])
        missing = list(chosen["blockers"])
    else:
        missing = sorted({blocker for item in evaluations for blocker in item["blockers"]})
    if selected:
        decision_reasons = [f"selected {selected['provider_id']} / {selected['package_id']} under {policy.version}"]
    elif classification["status"] in {"ambiguous_family", "unsupported_family"}:
        decision_reasons = list(classification["reasons"])
    else:
        decision_reasons = [f"no executable provider package under {policy.version}"]
    provisional = {
        "contract_version": "route-decision.v2",
        "job_sha256": _digest(model_job.to_dict()),
        "status": status,
        "family_classification": classification,
        "selected": selected,
        "candidate_evaluations": evaluations,
        "rejected_candidates": [{"provider_id": item["provider_id"], "package_id": item["package_id"], "reasons": item["rejection_reasons"]} for item in rejected],
        "missing_requirements": missing,
        "fallback_routes": fallback,
        "decision_reasons": decision_reasons,
        "routing_policy": policy.to_dict(),
    }
    return {**provisional, "decision_id": f"fmrd_{_digest(provisional)[:24]}"}
