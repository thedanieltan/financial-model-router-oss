from __future__ import annotations

from typing import Any

from fmr.core import ModelJob, route_job, routing_policy
from fmr.core.handoffs import compile_provider_handoff
from fmr.provider_plugins import PluginCatalog
from fmr.registry import ProviderRegistry
from fmr.organization import OrganizationPolicy


def prepare_handoff(job: ModelJob | dict[str, Any], *, policy_name: str | None = None, registry: ProviderRegistry | None = None, plugins: PluginCatalog | None = None, organization_policy: OrganizationPolicy | None = None) -> dict[str, Any]:
    model_job = organization_policy.normalize_job(job) if organization_policy and isinstance(job, dict) else (ModelJob.from_mapping(job) if isinstance(job, dict) else job)
    provider_registry = registry or (organization_policy.registry() if organization_policy else ProviderRegistry.builtins())
    policy = routing_policy(policy_name)
    if organization_policy:
        policy = organization_policy.effective_policy(policy)
    decision = route_job(model_job, registry=provider_registry, policy=policy)
    if decision["status"] == "selected":
        target = decision["selected"]
    elif decision["status"] == "no_route":
        candidates = [item for item in decision["candidate_evaluations"] if item["eligible"]]
        candidates.sort(key=lambda item: (-item["score"], item["provider_id"], item["package_id"]))
        if not candidates:
            raise ValueError("handoff cannot be prepared because every candidate violates a hard constraint")
        target = candidates[0]
    else:
        raise ValueError(f"handoff cannot be prepared from route status: {decision['status']}")
    registered = provider_registry.package(target["provider_id"], target["package_id"])
    payload = (plugins or PluginCatalog.installed()).adapter(registered.package.adapter_entry_point).compile(model_job, registered)
    return compile_provider_handoff(model_job, decision, registered, payload, registry=provider_registry)
