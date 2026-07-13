from __future__ import annotations

from importlib.resources import files
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from fmr import __version__
from fmr.api.models import FixtureSummaryPayload, ModelRequestPayload, ValidationResultPayload
from fmr.fixtures import list_fixtures, load_fixture
from fmr.model_specs import MODEL_DEFINITIONS
from fmr.plan import build_plan, validate_plan_payload
from fmr.router import route_request
from fmr.types import ModelRequest
from fmr.workbook import inspect_workbook_bytes

MAX_REQUEST_BYTES = 1_048_576
MAX_WORKBOOK_REQUEST_BYTES = 20 * 1024 * 1024


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


async def _read_limited_body(request: Request, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(
                status_code=413,
                detail={"code": "workbook_too_large", "message": f"workbook exceeds {limit} bytes"},
            )
        chunks.append(chunk)
    return b"".join(chunks)


def create_app() -> FastAPI:
    application = FastAPI(
        title="Financial Model Router Developer API",
        version=__version__,
        description=(
            "Local developer interface for deterministic model routing, readiness "
            "assessment, transformation planning and XLSX inspection."
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
            limit = (
                MAX_WORKBOOK_REQUEST_BYTES
                if request.url.path == "/api/v1/workbooks/inspect"
                else MAX_REQUEST_BYTES
            )
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
        return {"status": "ok", "service": "financial-model-router", "version": __version__}

    @application.get("/api/v1/model-families")
    def model_families() -> list[dict[str, Any]]:
        return [
            {
                "model_family": definition.model_family,
                "title": definition.title,
                "objective_terms": list(definition.objective_terms),
                "required_data": list(definition.required_data),
                "required_assumptions": list(definition.required_assumptions),
                "required_workbook_capabilities": list(definition.required_workbook_capabilities),
            }
            for definition in MODEL_DEFINITIONS
        ]

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
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_workbook", "message": str(exc)},
            ) from exc

    return application


app = create_app()
