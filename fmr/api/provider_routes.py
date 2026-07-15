from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from fmr.core import FAMILIES, ModelJob, create_model_intent, create_scope_confirmation, route_job, routing_policy
from fmr.core.receipts import validate_execution_result
from fmr.execution import DEFAULT_ORCHESTRATOR, ExecutionRequest
from fmr.provider_service import prepare_handoff
from fmr.registry import ProviderRegistry
from fmr.knowledge import KnowledgeRegistry
from fmr.scoping_evidence import apply_workbook_scope_evidence, derive_workbook_scope_evidence
from fmr.scoping_service import answer_scope_question, assess_model_intent, compile_confirmed_scope

router = APIRouter(prefix="/api/v2", tags=["provider routing"])


def _invalid(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail={"code": "invalid_provider_request", "message": str(exc)})


@router.get("/model-families")
def model_families_v2() -> list[dict[str, Any]]:
    return [item.to_dict() for item in FAMILIES]


@router.get("/providers")
def providers_v2() -> list[dict[str, Any]]:
    return [item.to_dict() for item in ProviderRegistry.builtins().providers()]


@router.get("/scoping/knowledge")
def scoping_knowledge() -> dict[str, Any]:
    return KnowledgeRegistry.builtins().to_dict()


@router.post("/scoping/intents")
def create_scoping_intent(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return create_model_intent(payload)
    except ValueError as exc:
        raise _invalid(exc) from exc


@router.post("/scoping/assessments")
def assess_scoping_intent(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return assess_model_intent(payload)
    except ValueError as exc:
        raise _invalid(exc) from exc


@router.post("/scoping/answers")
def answer_scoping_question(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        if set(payload) != {"intent", "question_id", "answer"}:
            raise ValueError("scope answer must contain intent, question_id and answer")
        return answer_scope_question(payload["intent"], payload["question_id"], payload["answer"])
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid(ValueError(str(exc))) from exc


@router.post("/scoping/confirmations")
def confirm_scoping_assessment(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        if set(payload) != {"assessment", "selected_family", "acknowledged_limitations"}:
            raise ValueError("scope confirmation must contain assessment, selected_family and acknowledged_limitations")
        return create_scope_confirmation(
            payload["assessment"],
            selected_family=payload["selected_family"],
            acknowledged_limitations=payload["acknowledged_limitations"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid(ValueError(str(exc))) from exc


@router.post("/scoping/jobs")
def compile_scoped_model_job(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        if set(payload) - {"assessment", "confirmation", "input_references"} or not {"assessment", "confirmation"}.issubset(payload):
            raise ValueError("scoped job must contain assessment and confirmation, with optional input_references")
        return compile_confirmed_scope(
            payload["assessment"],
            payload["confirmation"],
            input_references=payload.get("input_references"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid(ValueError(str(exc))) from exc


@router.post("/scoping/workbook-evidence")
def workbook_scope_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        if set(payload) != {"workbook_map"}:
            raise ValueError("workbook evidence request must contain workbook_map")
        return derive_workbook_scope_evidence(payload["workbook_map"])
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid(ValueError(str(exc))) from exc


@router.post("/scoping/workbook-intents")
def apply_scoping_workbook_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        if set(payload) != {"intent", "evidence", "workbook_map"}:
            raise ValueError("workbook intent request must contain intent, evidence and workbook_map")
        return apply_workbook_scope_evidence(payload["intent"], payload["evidence"], workbook_map=payload["workbook_map"])
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid(ValueError(str(exc))) from exc


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
