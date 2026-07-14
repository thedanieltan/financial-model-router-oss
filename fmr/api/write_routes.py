from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from fmr.providers.native_xlsx.workbook import (
    compile_workbook_write_plan,
    validate_workbook_write_plan_payload,
)


class WorkbookWritePlanRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["workbook-write-plan-request.v1"] = (
        "workbook-write-plan-request.v1"
    )
    realization_plan: dict[str, Any]
    write_context: dict[str, Any]


class WorkbookWritePlanValidationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    write_plan: dict[str, Any]
    realization_plan: dict[str, Any]
    write_context: dict[str, Any]


router = APIRouter(prefix="/api/v1/workbooks", tags=["workbook write planning"])


@router.post("/write-plans")
def compile_write_plan(payload: WorkbookWritePlanRequestPayload) -> dict[str, Any]:
    try:
        write_plan = compile_workbook_write_plan(
            payload.realization_plan,
            payload.write_context,
        )
        issues = validate_workbook_write_plan_payload(
            write_plan,
            realization_plan=payload.realization_plan,
            write_context=payload.write_context,
        )
        if issues:
            raise ValueError("compiled write plan is invalid: " + "; ".join(issues))
        return write_plan
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_write_plan_request", "message": str(exc)},
        ) from exc


@router.post("/write-plans/validate")
def validate_write_plan(payload: WorkbookWritePlanValidationPayload) -> dict[str, Any]:
    issues = validate_workbook_write_plan_payload(
        payload.write_plan,
        realization_plan=payload.realization_plan,
        write_context=payload.write_context,
    )
    return {"valid": not issues, "issues": list(issues)}
