from __future__ import annotations

import base64
import binascii
from pathlib import PurePath
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fmr.workbook import (
    execute_workbook_write_plan_bytes,
    validate_workbook_execution_receipt_payload,
)

MAX_EXECUTION_WORKBOOK_BYTES = 20 * 1024 * 1024


class WorkbookExecutionRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["workbook-execution-request.v1"] = (
        "workbook-execution-request.v1"
    )
    filename: str = Field(min_length=1, max_length=255)
    output_filename: str = Field(min_length=1, max_length=255)
    workbook_base64: str = Field(min_length=1)
    write_plan: dict[str, Any]


class WorkbookExecutionReceiptValidationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receipt: dict[str, Any]
    write_plan: dict[str, Any] | None = None


router = APIRouter(prefix="/api/v1/workbooks", tags=["workbook execution"])


@router.post("/executions")
def execute_workbook(payload: WorkbookExecutionRequestPayload) -> dict[str, Any]:
    filename = _safe_filename(payload.filename)
    output_filename = _safe_filename(payload.output_filename)
    try:
        workbook_bytes = base64.b64decode(payload.workbook_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_workbook_base64", "message": str(exc)},
        ) from exc
    if len(workbook_bytes) > MAX_EXECUTION_WORKBOOK_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "workbook_too_large",
                "message": f"decoded workbook exceeds {MAX_EXECUTION_WORKBOOK_BYTES} bytes",
            },
        )
    try:
        result = execute_workbook_write_plan_bytes(
            workbook_bytes,
            filename=filename,
            output_filename=output_filename,
            write_plan=payload.write_plan,
        )
    except (ImportError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "workbook_execution_failed", "message": str(exc)},
        ) from exc
    return {
        "contract_version": "workbook-execution-result.v1",
        "output_filename": output_filename,
        "workbook_base64": base64.b64encode(result.output_bytes).decode("ascii"),
        "receipt": result.receipt,
    }


@router.post("/execution-receipts/validate")
def validate_execution_receipt(
    payload: WorkbookExecutionReceiptValidationPayload,
) -> dict[str, Any]:
    issues = validate_workbook_execution_receipt_payload(
        payload.receipt,
        write_plan=payload.write_plan,
    )
    return {"valid": not issues, "issues": list(issues)}


def _safe_filename(value: str) -> str:
    name = PurePath(value).name
    if name != value or name in {"", ".", ".."}:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_filename", "message": "filename must be a basename"},
        )
    if not name.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_filename", "message": "filename must use .xlsx"},
        )
    return name
