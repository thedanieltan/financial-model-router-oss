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


class WorkbookTargetResolutionRequestPayload(BaseModel):
    """Workbook analysis and patch used for semantic target resolution."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["workbook-target-resolution-request.v1"] = (
        "workbook-target-resolution-request.v1"
    )
    workbook_analysis: dict[str, Any]
    workbook_patch: dict[str, Any]


class WorkbookTargetResolutionValidationPayload(BaseModel):
    """Resolution plus source contracts for deterministic validation."""

    model_config = ConfigDict(extra="forbid")

    target_resolution: dict[str, Any]
    workbook_analysis: dict[str, Any]
    workbook_patch: dict[str, Any]


class CoordinateLayoutParametersPayload(BaseModel):
    """Explicit variable dimensions required by coordinate planning."""

    model_config = ConfigDict(extra="forbid")

    forecast_period_count: int = Field(ge=1, le=60)


class WorkbookCoordinatePlanRequestPayload(BaseModel):
    """Source contracts and layout parameters for coordinate planning."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["workbook-coordinate-plan-request.v1"] = (
        "workbook-coordinate-plan-request.v1"
    )
    analysis: dict[str, Any]
    patch: dict[str, Any]
    target_resolution: dict[str, Any]
    layout_parameters: CoordinateLayoutParametersPayload


class WorkbookCoordinatePlanValidationPayload(BaseModel):
    """Coordinate plan plus source contracts for deterministic validation."""

    model_config = ConfigDict(extra="forbid")

    coordinate_plan: dict[str, Any]
    analysis: dict[str, Any]
    patch: dict[str, Any]
    target_resolution: dict[str, Any]
    layout_parameters: CoordinateLayoutParametersPayload


class WorkbookContentPlanRequestPayload(BaseModel):
    """Coordinate plan used to compile symbolic workbook content."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["workbook-content-plan-request.v1"] = (
        "workbook-content-plan-request.v1"
    )
    coordinate_plan: dict[str, Any]


class WorkbookContentPlanValidationPayload(BaseModel):
    """Content plan plus its source coordinate plan."""

    model_config = ConfigDict(extra="forbid")

    content_plan: dict[str, Any]
    coordinate_plan: dict[str, Any]


class WorkbookRealizationPlanRequestPayload(BaseModel):
    """Content plan used to bind formula dependencies and declarative styles."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["workbook-realization-plan-request.v1"] = (
        "workbook-realization-plan-request.v1"
    )
    content_plan: dict[str, Any]


class WorkbookRealizationPlanValidationPayload(BaseModel):
    """Realization plan plus its source content plan."""

    model_config = ConfigDict(extra="forbid")

    realization_plan: dict[str, Any]
    content_plan: dict[str, Any]


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
