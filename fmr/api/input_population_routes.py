from __future__ import annotations

import base64
import binascii
from pathlib import PurePath
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fmr.providers.native_xlsx.workbook import (
    compile_workbook_input_set_from_csv,
    populate_workbook_inputs_bytes,
    validate_input_population_calculation_link,
    validate_workbook_input_population_receipt_payload,
    validate_workbook_input_set_payload,
)

MAX_POPULATION_WORKBOOK_BYTES = 20 * 1024 * 1024
MAX_INPUT_CSV_BYTES = 2 * 1024 * 1024


class WorkbookInputSetCsvRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["workbook-input-set-csv-request.v1"] = (
        "workbook-input-set-csv-request.v1"
    )
    source_name: str = Field(min_length=1, max_length=255)
    csv_base64: str = Field(min_length=1)
    write_plan: dict[str, Any]
    execution_receipt: dict[str, Any]


class WorkbookInputSetValidationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_set: dict[str, Any]
    write_plan: dict[str, Any] | None = None
    execution_receipt: dict[str, Any] | None = None


class WorkbookInputPopulationRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["workbook-input-population-request.v1"] = (
        "workbook-input-population-request.v1"
    )
    filename: str = Field(min_length=1, max_length=255)
    output_filename: str = Field(min_length=1, max_length=255)
    workbook_base64: str = Field(min_length=1)
    write_plan: dict[str, Any]
    execution_receipt: dict[str, Any]
    input_set: dict[str, Any]


class WorkbookInputPopulationReceiptValidationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receipt: dict[str, Any]
    input_set: dict[str, Any] | None = None
    write_plan: dict[str, Any] | None = None
    execution_receipt: dict[str, Any] | None = None


class WorkbookInputCalculationLinkValidationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    population_receipt: dict[str, Any]
    calculation_acceptance: dict[str, Any]


router = APIRouter(prefix="/api/v1/workbooks", tags=["workbook input population"])


@router.post("/input-sets/from-csv")
def compile_input_set_csv(
    payload: WorkbookInputSetCsvRequestPayload,
) -> dict[str, Any]:
    csv_bytes = _decode(
        payload.csv_base64,
        "csv_base64",
        maximum=MAX_INPUT_CSV_BYTES,
    )
    try:
        return compile_workbook_input_set_from_csv(
            csv_bytes,
            source_name=PurePath(payload.source_name).name,
            write_plan=payload.write_plan,
            execution_receipt=payload.execution_receipt,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "input_set_compilation_failed", "message": str(exc)},
        ) from exc


@router.post("/input-sets/validate")
def validate_input_set(
    payload: WorkbookInputSetValidationPayload,
) -> dict[str, Any]:
    issues = validate_workbook_input_set_payload(
        payload.input_set,
        write_plan=payload.write_plan,
        execution_receipt=payload.execution_receipt,
    )
    return {"valid": not issues, "issues": list(issues)}


@router.post("/input-populations")
def populate_inputs(
    payload: WorkbookInputPopulationRequestPayload,
) -> dict[str, Any]:
    filename = _safe_xlsx_filename(payload.filename)
    output_filename = _safe_xlsx_filename(payload.output_filename)
    workbook_bytes = _decode(
        payload.workbook_base64,
        "workbook_base64",
        maximum=MAX_POPULATION_WORKBOOK_BYTES,
    )
    try:
        result = populate_workbook_inputs_bytes(
            workbook_bytes,
            filename=filename,
            output_filename=output_filename,
            write_plan=payload.write_plan,
            execution_receipt=payload.execution_receipt,
            input_set=payload.input_set,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "input_population_failed", "message": str(exc)},
        ) from exc
    return {
        "contract_version": "workbook-input-population-result.v1",
        "output_filename": output_filename,
        "workbook_base64": base64.b64encode(result.output_bytes).decode("ascii"),
        "receipt": result.receipt,
    }


@router.post("/input-population-receipts/validate")
def validate_population_receipt(
    payload: WorkbookInputPopulationReceiptValidationPayload,
) -> dict[str, Any]:
    issues = validate_workbook_input_population_receipt_payload(
        payload.receipt,
        input_set=payload.input_set,
        write_plan=payload.write_plan,
        execution_receipt=payload.execution_receipt,
    )
    return {"valid": not issues, "issues": list(issues)}


@router.post("/input-population-receipts/validate-calculation-link")
def validate_population_calculation_link(
    payload: WorkbookInputCalculationLinkValidationPayload,
) -> dict[str, Any]:
    issues = validate_input_population_calculation_link(
        payload.population_receipt,
        payload.calculation_acceptance,
    )
    return {"valid": not issues, "issues": list(issues)}


def _decode(value: str, field: str, *, maximum: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_base64", "message": f"{field}: {exc}"},
        ) from exc
    if not decoded:
        raise HTTPException(
            status_code=422,
            detail={"code": "empty_payload", "message": f"{field} is empty"},
        )
    if len(decoded) > maximum:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "payload_too_large",
                "message": f"{field} exceeds {maximum} bytes",
            },
        )
    return decoded


def _safe_xlsx_filename(value: str) -> str:
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
