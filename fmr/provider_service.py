from __future__ import annotations

from typing import Any

from fmr.core import ModelJob, route_job, routing_policy
from fmr.core.handoffs import compile_provider_handoff
from fmr.provider_adapters import compile_provider_payload
from fmr.registry import ProviderRegistry


def prepare_handoff(job: ModelJob | dict[str, Any], *, policy_name: str | None = None, registry: ProviderRegistry | None = None) -> dict[str, Any]:
    model_job = ModelJob.from_mapping(job) if isinstance(job, dict) else job
    provider_registry = registry or ProviderRegistry.builtins()
    decision = route_job(model_job, registry=provider_registry, policy=routing_policy(policy_name))
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
    payload = compile_provider_payload(model_job, registered)
    return compile_provider_handoff(model_job, decision, registered, payload)
