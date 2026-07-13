from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelRequestPayload(BaseModel):
    """HTTP representation of ``model-request.v1``."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["model-request.v1"] = "model-request.v1"
    objective: str = Field(min_length=1, max_length=1_000)
    role: str = Field(min_length=1, max_length=200)
    available_data: list[str] = Field(default_factory=list)
    workbook_capabilities: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class WorkbookAnalysisRequestPayload(BaseModel):
    """Composite request for evidence-backed workbook analysis."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["workbook-analysis-request.v1"] = (
        "workbook-analysis-request.v1"
    )
    workbook_map: dict[str, Any]
    model_request: ModelRequestPayload


class WorkbookPatchReceiptValidationPayload(BaseModel):
    """Receipt with an optional patch for cross-contract validation."""

    model_config = ConfigDict(extra="forbid")

    receipt: dict[str, Any]
    patch: dict[str, Any] | None = None


class ValidationResultPayload(BaseModel):
    valid: bool
    issues: list[str]


class FixtureSummaryPayload(BaseModel):
    fixture_id: str
    title: str
    description: str


class ErrorPayload(BaseModel):
    valid: Literal[False] = False
    error: str
    details: dict[str, Any] | None = None
