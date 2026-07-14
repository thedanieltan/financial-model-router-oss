from __future__ import annotations

from importlib.resources import files
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from fmr import __version__
from fmr.api.models import (
    FixtureSummaryPayload,
    ModelRequestPayload,
    ValidationResultPayload,
    WorkbookAnalysisRequestPayload,
    WorkbookContentPlanRequestPayload,
    WorkbookContentPlanValidationPayload,
    WorkbookCoordinatePlanRequestPayload,
    WorkbookCoordinatePlanValidationPayload,
    WorkbookPatchReceiptValidationPayload,
    WorkbookRealizationPlanRequestPayload,
    WorkbookRealizationPlanValidationPayload,
    WorkbookTargetResolutionRequestPayload,
    WorkbookTargetResolutionValidationPayload,
)
from fmr.fixtures import list_fixtures, load_fixture
from fmr.model_specs import MODEL_DEFINITIONS
from fmr.plan import build_plan, validate_plan_payload
from fmr.router import route_request
from fmr.types import ModelRequest
from fmr.providers.native_xlsx.workbook import (
    WorkbookAnalysis,
    WorkbookMap,
    analyse_workbook_map,
    compile_workbook_patch,
    content_spec_registry_payload,
    coordinate_rule_registry_payload,
    formula_spec_registry_payload,
    inspect_workbook_bytes,
    operation_spec_registry_payload,
    plan_workbook_content,
    plan_workbook_coordinates,
    plan_workbook_realization,
    resolve_workbook_patch_targets,
    style_spec_registry_payload,
    validate_workbook_content_plan_payload,
    validate_workbook_coordinate_plan_payload,
    validate_workbook_patch_payload,
    validate_workbook_patch_receipt_payload,
    validate_workbook_realization_plan_payload,
    validate_workbook_target_resolution_payload,
)

MAX_REQUEST_BYTES = 1_048_576
MAX_WORKBOOK_MAP_REQUEST_BYTES = 5 * 1024 * 1024
MAX_WORKBOOK_REQUEST_BYTES = 20 * 1024 * 1024
_WORKBOOK_JSON_PATHS = {
    "/api/v1/workbooks/analyse",
    "/api/v1/workbooks/patches",
    "/api/v1/workbooks/target-resolutions",
    "/api/v1/workbooks/target-resolutions/validate",
    "/api/v1/workbooks/coordinate-plans",
    "/api/v1/workbooks/coordinate-plans/validate",
    "/api/v1/workbooks/content-plans",
    "/api/v1/workbooks/content-plans/validate",
    "/api/v1/workbooks/realization-plans",
    "/api/v1/workbooks/realization-plans/validate",
}


def _asset(name: str) -> str:
    return files("fmr.web").joinpath(name).read_text(encoding="utf-8")


def _request_from_payload(payload: ModelRequestPayload) -> ModelRequest:
    return ModelRequest.from_mapping(payload.model_dump(mode="json"))


def _execute_request(payload: ModelRequestPayload, *, plan: bool) -> dict[str, Any]:
    try:
        request = _request_from_payload(payload)
        result = build_plan(request) if plan else route_request(request)
        return result.to_dict()
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_model_request", "message": str(exc)},
        ) from exc


def _contract_error(code: str, exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"code": code, "message": str(exc)},
    )


async def _read_limited_body(request: Request, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "workbook_too_large",
                    "message": f"workbook exceeds {limit} bytes",
                },
            )
        chunks.append(chunk)
    return b"".join(chunks)


def create_app() -> FastAPI:
    application = FastAPI(
        title="Financial Model Router Developer API",
        version=__version__,
        description=(
            "Local developer interface for deterministic provider routing, handoff "
            "and execution alongside the Native XLSX compatibility workflow."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @application.middleware("http")
    async def limit_request_size(request: Request, call_next):  # type: ignore[no-untyped-def]
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                size = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"valid": False, "error": "invalid Content-Length header"},
                )
            if request.url.path == "/api/v1/workbooks/inspect":
                limit = MAX_WORKBOOK_REQUEST_BYTES
            elif request.url.path in _WORKBOOK_JSON_PATHS:
                limit = MAX_WORKBOOK_MAP_REQUEST_BYTES
            else:
                limit = MAX_REQUEST_BYTES
            if size > limit:
                return JSONResponse(
                    status_code=413,
                    content={"valid": False, "error": f"request exceeds {limit} bytes"},
                )
        return await call_next(request)

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    def workbench() -> str:
        return _asset("index.html")

    @application.get("/assets/app.js", include_in_schema=False)
    def javascript() -> Response:
        return Response(_asset("app.js"), media_type="application/javascript")

    @application.get("/assets/styles.css", include_in_schema=False)
    def stylesheet() -> Response:
        return Response(_asset("styles.css"), media_type="text/css")

    @application.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "financial-model-router",
            "version": __version__,
        }

    @application.get("/api/v1/model-families")
    def model_families() -> list[dict[str, Any]]:
        return [
            {
                "model_family": definition.model_family,
                "title": definition.title,
                "objective_terms": list(definition.objective_terms),
                "required_data": list(definition.required_data),
                "required_assumptions": list(definition.required_assumptions),
                "required_workbook_capabilities": list(
                    definition.required_workbook_capabilities
                ),
            }
            for definition in MODEL_DEFINITIONS
        ]

    @application.get("/api/v1/workbook-operation-specs")
    def workbook_operation_specs() -> dict[str, Any]:
        return operation_spec_registry_payload()

    @application.get("/api/v1/workbook-coordinate-rules")
    def workbook_coordinate_rules() -> dict[str, Any]:
        return coordinate_rule_registry_payload()

    @application.get("/api/v1/workbook-content-specs")
    def workbook_content_specs() -> dict[str, Any]:
        return content_spec_registry_payload()

    @application.get("/api/v1/workbook-formula-specs")
    def workbook_formula_specs() -> dict[str, Any]:
        return formula_spec_registry_payload()

    @application.get("/api/v1/workbook-style-specs")
    def workbook_style_specs() -> dict[str, Any]:
        return style_spec_registry_payload()

    @application.get("/api/v1/fixtures", response_model=list[FixtureSummaryPayload])
    def fixtures() -> list[dict[str, str]]:
        return list_fixtures()

    @application.get("/api/v1/fixtures/{fixture_id}")
    def fixture(fixture_id: str) -> dict[str, Any]:
        try:
            return load_fixture(fixture_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post("/api/v1/route")
    def route(payload: ModelRequestPayload) -> dict[str, Any]:
        return _execute_request(payload, plan=False)

    @application.post("/api/v1/plan")
    def plan(payload: ModelRequestPayload) -> dict[str, Any]:
        return _execute_request(payload, plan=True)

    @application.post("/api/v1/validate-plan", response_model=ValidationResultPayload)
    def validate_plan(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        issues = validate_plan_payload(payload)
        return {"valid": not issues, "issues": list(issues)}

    @application.post("/api/v1/workbooks/inspect")
    async def inspect_uploaded_workbook(request: Request, filename: str) -> dict[str, Any]:
        data = await _read_limited_body(request, MAX_WORKBOOK_REQUEST_BYTES)
        try:
            return inspect_workbook_bytes(data, filename=filename).to_dict()
        except ValueError as exc:
            raise _contract_error("invalid_workbook", exc) from exc

    @application.post("/api/v1/workbooks/analyse")
    def analyse_mapped_workbook(payload: WorkbookAnalysisRequestPayload) -> dict[str, Any]:
        try:
            workbook_map = WorkbookMap.from_mapping(payload.workbook_map)
            model_request = _request_from_payload(payload.model_request)
            return analyse_workbook_map(workbook_map, model_request).to_dict()
        except ValueError as exc:
            raise _contract_error("invalid_workbook_analysis_request", exc) from exc

    @application.post("/api/v1/workbooks/patches")
    def compile_patch(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            analysis = WorkbookAnalysis.from_mapping(payload)
            patch = compile_workbook_patch(analysis).to_dict()
            issues = validate_workbook_patch_payload(patch)
            if issues:
                raise ValueError(f"compiled patch is invalid: {'; '.join(issues)}")
            return patch
        except ValueError as exc:
            raise _contract_error("invalid_workbook_patch_request", exc) from exc

    @application.post(
        "/api/v1/workbooks/patches/validate",
        response_model=ValidationResultPayload,
    )
    def validate_patch(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        issues = validate_workbook_patch_payload(payload)
        return {"valid": not issues, "issues": list(issues)}

    @application.post(
        "/api/v1/workbooks/patch-receipts/validate",
        response_model=ValidationResultPayload,
    )
    def validate_patch_receipt(
        payload: WorkbookPatchReceiptValidationPayload,
    ) -> dict[str, Any]:
        issues = validate_workbook_patch_receipt_payload(
            payload.receipt,
            patch=payload.patch,
        )
        return {"valid": not issues, "issues": list(issues)}

    @application.post("/api/v1/workbooks/target-resolutions")
    def resolve_targets(
        payload: WorkbookTargetResolutionRequestPayload,
    ) -> dict[str, Any]:
        try:
            analysis = WorkbookAnalysis.from_mapping(payload.workbook_analysis)
            resolution = resolve_workbook_patch_targets(
                analysis,
                payload.workbook_patch,
            ).to_dict()
            issues = validate_workbook_target_resolution_payload(
                resolution,
                analysis=analysis,
                patch=payload.workbook_patch,
            )
            if issues:
                raise ValueError(
                    f"compiled target resolution is invalid: {'; '.join(issues)}"
                )
            return resolution
        except ValueError as exc:
            raise _contract_error("invalid_target_resolution_request", exc) from exc

    @application.post(
        "/api/v1/workbooks/target-resolutions/validate",
        response_model=ValidationResultPayload,
    )
    def validate_target_resolution(
        payload: WorkbookTargetResolutionValidationPayload,
    ) -> dict[str, Any]:
        try:
            analysis = WorkbookAnalysis.from_mapping(payload.workbook_analysis)
        except ValueError as exc:
            raise _contract_error(
                "invalid_target_resolution_validation_request",
                exc,
            ) from exc
        issues = validate_workbook_target_resolution_payload(
            payload.target_resolution,
            analysis=analysis,
            patch=payload.workbook_patch,
        )
        return {"valid": not issues, "issues": list(issues)}

    @application.post("/api/v1/workbooks/coordinate-plans")
    def compile_coordinate_plan(
        payload: WorkbookCoordinatePlanRequestPayload,
    ) -> dict[str, Any]:
        try:
            analysis = WorkbookAnalysis.from_mapping(payload.analysis)
            count = payload.layout_parameters.forecast_period_count
            coordinate_plan = plan_workbook_coordinates(
                analysis,
                payload.patch,
                payload.target_resolution,
                forecast_period_count=count,
            )
            issues = validate_workbook_coordinate_plan_payload(
                coordinate_plan,
                analysis=analysis,
                patch=payload.patch,
                target_resolution=payload.target_resolution,
                forecast_period_count=count,
            )
            if issues:
                raise ValueError(
                    f"compiled coordinate plan is invalid: {'; '.join(issues)}"
                )
            return coordinate_plan
        except ValueError as exc:
            raise _contract_error("invalid_coordinate_plan_request", exc) from exc

    @application.post(
        "/api/v1/workbooks/coordinate-plans/validate",
        response_model=ValidationResultPayload,
    )
    def validate_coordinate_plan(
        payload: WorkbookCoordinatePlanValidationPayload,
    ) -> dict[str, Any]:
        try:
            analysis = WorkbookAnalysis.from_mapping(payload.analysis)
        except ValueError as exc:
            raise _contract_error(
                "invalid_coordinate_plan_validation_request",
                exc,
            ) from exc
        issues = validate_workbook_coordinate_plan_payload(
            payload.coordinate_plan,
            analysis=analysis,
            patch=payload.patch,
            target_resolution=payload.target_resolution,
            forecast_period_count=payload.layout_parameters.forecast_period_count,
        )
        return {"valid": not issues, "issues": list(issues)}

    @application.post("/api/v1/workbooks/content-plans")
    def compile_content_plan(
        payload: WorkbookContentPlanRequestPayload,
    ) -> dict[str, Any]:
        try:
            content_plan = plan_workbook_content(payload.coordinate_plan)
            issues = validate_workbook_content_plan_payload(
                content_plan,
                coordinate_plan=payload.coordinate_plan,
            )
            if issues:
                raise ValueError(
                    f"compiled content plan is invalid: {'; '.join(issues)}"
                )
            return content_plan
        except ValueError as exc:
            raise _contract_error("invalid_content_plan_request", exc) from exc

    @application.post(
        "/api/v1/workbooks/content-plans/validate",
        response_model=ValidationResultPayload,
    )
    def validate_content_plan(
        payload: WorkbookContentPlanValidationPayload,
    ) -> dict[str, Any]:
        issues = validate_workbook_content_plan_payload(
            payload.content_plan,
            coordinate_plan=payload.coordinate_plan,
        )
        return {"valid": not issues, "issues": list(issues)}

    @application.post("/api/v1/workbooks/realization-plans")
    def compile_realization_plan(
        payload: WorkbookRealizationPlanRequestPayload,
    ) -> dict[str, Any]:
        try:
            realization_plan = plan_workbook_realization(payload.content_plan)
            issues = validate_workbook_realization_plan_payload(
                realization_plan,
                content_plan=payload.content_plan,
            )
            if issues:
                raise ValueError(
                    f"compiled realization plan is invalid: {'; '.join(issues)}"
                )
            return realization_plan
        except ValueError as exc:
            raise _contract_error("invalid_realization_plan_request", exc) from exc

    @application.post(
        "/api/v1/workbooks/realization-plans/validate",
        response_model=ValidationResultPayload,
    )
    def validate_realization_plan(
        payload: WorkbookRealizationPlanValidationPayload,
    ) -> dict[str, Any]:
        issues = validate_workbook_realization_plan_payload(
            payload.realization_plan,
            content_plan=payload.content_plan,
        )
        return {"valid": not issues, "issues": list(issues)}

    return application


app = create_app()
