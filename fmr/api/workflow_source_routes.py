from __future__ import annotations

import base64
import binascii
from pathlib import PurePath
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from fmr.financial_data import (
    create_statement_csv_workflow_source,
    statement_csv_template,
)

MAX_WORKFLOW_SOURCE_BYTES = 5 * 1024 * 1024


class WorkflowStatementCsvRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["workflow-statement-csv-request.v1"] = (
        "workflow-statement-csv-request.v1"
    )
    source_name: str = Field(min_length=1, max_length=255)
    csv_base64: str = Field(min_length=1)
    mapping_rules: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    operational_drivers: dict[str, list[Any]] = Field(default_factory=dict)


router = APIRouter(prefix="/api/v2/workflow-sources", tags=["workflow sources"])


@router.get("/statement-csv-template", include_in_schema=False)
def download_statement_csv_template() -> Response:
    return Response(
        statement_csv_template(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="fmr-statement-source-template.csv"'
        },
    )


@router.post("/statement-csv")
def create_statement_csv_source(
    payload: WorkflowStatementCsvRequest,
) -> dict[str, Any]:
    try:
        csv_bytes = _decode(payload.csv_base64)
        return create_statement_csv_workflow_source(
            csv_bytes,
            source_name=PurePath(payload.source_name).name,
            mapping_rules=payload.mapping_rules,
            assumptions=payload.assumptions,
            operational_drivers=payload.operational_drivers,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "workflow_source_invalid", "message": str(exc)},
        ) from exc
    except (OSError, RuntimeError) as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "workflow_source_storage_failed", "message": str(exc)},
        ) from exc


def _decode(value: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("csv_base64 is invalid") from exc
    if not decoded:
        raise ValueError("statement CSV payload is empty")
    if len(decoded) > MAX_WORKFLOW_SOURCE_BYTES:
        raise ValueError(
            f"statement CSV exceeds {MAX_WORKFLOW_SOURCE_BYTES} bytes"
        )
    return decoded


__all__ = ["MAX_WORKFLOW_SOURCE_BYTES", "WorkflowStatementCsvRequest", "router"]
