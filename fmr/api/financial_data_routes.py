from __future__ import annotations

import base64
import binascii
from pathlib import PurePath
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fmr.financial_data import (
    build_binding_profile,
    build_mapping_profile,
    compile_input_set_from_binding_plan,
    concept_registry_payload,
    import_statement_csv,
    map_financial_data,
    plan_financial_input_bindings,
    validate_binding_plan,
    validate_financial_data_package,
    validate_mapping_result,
)

MAX_STATEMENT_CSV_BYTES = 5 * 1024 * 1024


class StatementCsvRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["financial-data-csv-request.v1"] = (
        "financial-data-csv-request.v1"
    )
    source_name: str = Field(min_length=1, max_length=255)
    csv_base64: str = Field(min_length=1)


class MappingProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    rules: list[dict[str, Any]]


class MappingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: dict[str, Any]
    profile: dict[str, Any] | None = None


class BindingProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    bindings: list[dict[str, Any]]


class BindingPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: dict[str, Any]
    mapping_result: dict[str, Any]
    binding_profile: dict[str, Any]
    write_plan: dict[str, Any]
    execution_receipt: dict[str, Any]


class InputSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binding_plan: dict[str, Any]
    write_plan: dict[str, Any]
    execution_receipt: dict[str, Any]


class PackageValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: dict[str, Any]


class MappingValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mapping_result: dict[str, Any]
    package: dict[str, Any] | None = None
    profile: dict[str, Any] | None = None


class BindingPlanValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binding_plan: dict[str, Any]
    package: dict[str, Any] | None = None
    mapping_result: dict[str, Any] | None = None
    binding_profile: dict[str, Any] | None = None
    write_plan: dict[str, Any] | None = None
    execution_receipt: dict[str, Any] | None = None


router = APIRouter(prefix="/api/v1", tags=["financial data intake"])


@router.get("/financial-concepts")
def financial_concepts() -> dict[str, Any]:
    return concept_registry_payload()


@router.post("/financial-data/packages/from-csv")
def import_financial_data(payload: StatementCsvRequest) -> dict[str, Any]:
    csv_bytes = _decode(payload.csv_base64)
    try:
        return import_statement_csv(
            csv_bytes,
            source_name=PurePath(payload.source_name).name,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "financial_data_import_failed", "message": str(exc)},
        ) from exc


@router.post("/financial-data/mapping-profiles")
def create_mapping_profile(payload: MappingProfileRequest) -> dict[str, Any]:
    try:
        return build_mapping_profile(payload.rules, name=payload.name)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "mapping_profile_invalid", "message": str(exc)},
        ) from exc


@router.post("/financial-data/mappings")
def create_mapping(payload: MappingRequest) -> dict[str, Any]:
    try:
        return map_financial_data(payload.package, profile=payload.profile)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "financial_mapping_failed", "message": str(exc)},
        ) from exc


@router.post("/financial-data/binding-profiles")
def create_binding_profile(payload: BindingProfileRequest) -> dict[str, Any]:
    try:
        return build_binding_profile(payload.bindings, name=payload.name)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "binding_profile_invalid", "message": str(exc)},
        ) from exc


@router.post("/financial-data/binding-plans")
def create_binding_plan(payload: BindingPlanRequest) -> dict[str, Any]:
    try:
        return plan_financial_input_bindings(
            payload.package,
            payload.mapping_result,
            payload.binding_profile,
            write_plan=payload.write_plan,
            execution_receipt=payload.execution_receipt,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "financial_binding_failed", "message": str(exc)},
        ) from exc


@router.post("/financial-data/input-sets")
def create_financial_input_set(payload: InputSetRequest) -> dict[str, Any]:
    try:
        return compile_input_set_from_binding_plan(
            payload.binding_plan,
            write_plan=payload.write_plan,
            execution_receipt=payload.execution_receipt,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "financial_input_set_failed", "message": str(exc)},
        ) from exc


@router.post("/financial-data/packages/validate")
def validate_package(payload: PackageValidationRequest) -> dict[str, Any]:
    issues = validate_financial_data_package(payload.package)
    return {"valid": not issues, "issues": list(issues)}


@router.post("/financial-data/mappings/validate")
def validate_mapping(payload: MappingValidationRequest) -> dict[str, Any]:
    issues = validate_mapping_result(
        payload.mapping_result,
        package=payload.package,
        profile=payload.profile,
    )
    return {"valid": not issues, "issues": list(issues)}


@router.post("/financial-data/binding-plans/validate")
def validate_binding(payload: BindingPlanValidationRequest) -> dict[str, Any]:
    issues = validate_binding_plan(
        payload.binding_plan,
        package=payload.package,
        mapping_result=payload.mapping_result,
        binding_profile=payload.binding_profile,
        write_plan=payload.write_plan,
        execution_receipt=payload.execution_receipt,
    )
    return {"valid": not issues, "issues": list(issues)}


def _decode(value: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_base64", "message": str(exc)},
        ) from exc
    if not decoded:
        raise HTTPException(
            status_code=422,
            detail={"code": "empty_payload", "message": "CSV payload is empty"},
        )
    if len(decoded) > MAX_STATEMENT_CSV_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "payload_too_large",
                "message": f"CSV exceeds {MAX_STATEMENT_CSV_BYTES} bytes",
            },
        )
    return decoded
