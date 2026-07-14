from __future__ import annotations

import base64
import binascii
from pathlib import PurePath
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fmr.providers.native_xlsx.workbook import (
    accept_calculated_workbook_bytes,
    calculate_and_accept_workbook_bytes,
    calculation_engine_status,
    validate_workbook_calculation_acceptance_payload,
)

MAX_CALCULATION_WORKBOOK_BYTES = 20 * 1024 * 1024


class WorkbookCalculationRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["workbook-calculation-request.v1"] = (
        "workbook-calculation-request.v1"
    )
    filename: str = Field(min_length=1, max_length=255)
    output_filename: str = Field(min_length=1, max_length=255)
    workbook_base64: str = Field(min_length=1)
    write_plan: dict[str, Any]
    execution_receipt: dict[str, Any]
    timeout_seconds: int = Field(default=120, ge=1, le=600)


class ExternalCalculationAcceptancePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["external-calculation-acceptance-request.v1"] = (
        "external-calculation-acceptance-request.v1"
    )
    input_filename: str = Field(min_length=1, max_length=255)
    output_filename: str = Field(min_length=1, max_length=255)
    input_workbook_base64: str = Field(min_length=1)
    calculated_workbook_base64: str = Field(min_length=1)
    write_plan: dict[str, Any]
    execution_receipt: dict[str, Any]
    engine_name: str = Field(min_length=1, max_length=200)
    engine_version: str = Field(min_length=1, max_length=500)


class CalculationAcceptanceValidationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acceptance: dict[str, Any]
    write_plan: dict[str, Any] | None = None
    execution_receipt: dict[str, Any] | None = None


router = APIRouter(prefix="/api/v1", tags=["calculated output acceptance"])


@router.get("/calculation-engine")
def calculation_engine() -> dict[str, Any]:
    return calculation_engine_status()


@router.post("/workbooks/calculations")
def calculate_workbook(payload: WorkbookCalculationRequestPayload) -> dict[str, Any]:
    filename = _safe_filename(payload.filename)
    output_filename = _safe_filename(payload.output_filename)
    workbook_bytes = _decode(payload.workbook_base64, "workbook_base64")
    try:
        result = calculate_and_accept_workbook_bytes(
            workbook_bytes,
            input_filename=filename,
            output_filename=output_filename,
            write_plan=payload.write_plan,
            execution_receipt=payload.execution_receipt,
            timeout_seconds=payload.timeout_seconds,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "workbook_calculation_failed", "message": str(exc)},
        ) from exc
    return {
        "contract_version": "workbook-calculation-result.v1",
        "output_filename": output_filename,
        "workbook_base64": (
            base64.b64encode(result.output_bytes).decode("ascii")
            if result.receipt["status"] == "passed"
            else None
        ),
        "acceptance": result.receipt,
    }


@router.post("/workbooks/calculation-acceptances")
def accept_external_calculation(
    payload: ExternalCalculationAcceptancePayload,
) -> dict[str, Any]:
    input_filename = _safe_filename(payload.input_filename)
    output_filename = _safe_filename(payload.output_filename)
    input_bytes = _decode(payload.input_workbook_base64, "input_workbook_base64")
    calculated_bytes = _decode(
        payload.calculated_workbook_base64,
        "calculated_workbook_base64",
    )
    try:
        return accept_calculated_workbook_bytes(
            input_bytes,
            calculated_bytes,
            input_filename=input_filename,
            output_filename=output_filename,
            write_plan=payload.write_plan,
            execution_receipt=payload.execution_receipt,
            engine={
                "name": payload.engine_name,
                "version": payload.engine_version,
                "adapter": "external-calculation.v1",
            },
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "calculation_acceptance_failed", "message": str(exc)},
        ) from exc


@router.post("/workbooks/calculation-acceptances/validate")
def validate_calculation_acceptance(
    payload: CalculationAcceptanceValidationPayload,
) -> dict[str, Any]:
    issues = validate_workbook_calculation_acceptance_payload(
        payload.acceptance,
        write_plan=payload.write_plan,
        execution_receipt=payload.execution_receipt,
    )
    return {"valid": not issues, "issues": list(issues)}


def _decode(value: str, field: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_base64", "message": f"{field}: {exc}"},
        ) from exc
    if len(decoded) > MAX_CALCULATION_WORKBOOK_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "workbook_too_large",
                "message": f"{field} exceeds {MAX_CALCULATION_WORKBOOK_BYTES} bytes",
            },
        )
    if not decoded:
        raise HTTPException(
            status_code=422,
            detail={"code": "empty_workbook", "message": f"{field} is empty"},
        )
    return decoded


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
