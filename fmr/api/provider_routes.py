from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from fmr.core import FAMILIES, ModelJob, route_job, routing_policy
from fmr.core.receipts import validate_execution_result
from fmr.execution import DEFAULT_ORCHESTRATOR, ExecutionRequest
from fmr.provider_service import prepare_handoff
from fmr.registry import ProviderRegistry

router = APIRouter(prefix="/api/v2", tags=["provider routing"])


def _invalid(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail={"code": "invalid_provider_request", "message": str(exc)})


@router.get("/model-families")
def model_families_v2() -> list[dict[str, Any]]:
    return [item.to_dict() for item in FAMILIES]


@router.get("/providers")
def providers_v2() -> list[dict[str, Any]]:
    return [item.to_dict() for item in ProviderRegistry.builtins().providers()]


@router.post("/jobs/routes")
def route_model_job(payload: dict[str, Any], policy: str = Query("default")) -> dict[str, Any]:
    try:
        return route_job(ModelJob.from_mapping(payload), policy=routing_policy(policy))
    except ValueError as exc:
        raise _invalid(exc) from exc


@router.post("/jobs/handoffs")
def prepare_model_handoff(payload: dict[str, Any], policy: str = Query("default")) -> dict[str, Any]:
    try:
        return prepare_handoff(payload, policy_name=policy)
    except ValueError as exc:
        raise _invalid(exc) from exc


@router.post("/jobs/executions")
def execute_model_job(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        request = ExecutionRequest.from_mapping(payload)
        if request.output_policy.mode != "managed":
            raise ValueError("HTTP execution supports managed output policy only")
        return DEFAULT_ORCHESTRATOR.execute_request(request)
    except (ValueError, RuntimeError) as exc:
        raise _invalid(ValueError(str(exc))) from exc


@router.post("/job-results/validate")
def validate_model_job_result(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) != {"result", "handoff"}:
        raise _invalid(ValueError("validation payload must contain result and handoff"))
    issues = validate_execution_result(payload["result"], handoff=payload["handoff"])
    return {"valid": not issues, "issues": list(issues)}
