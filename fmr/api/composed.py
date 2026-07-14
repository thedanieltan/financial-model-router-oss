from __future__ import annotations

from importlib.resources import files

from fastapi import FastAPI, Request
from fastapi.responses import Response

from fmr.api.app import create_app as create_base_app
from fmr.api.calculation_routes import router as calculation_router
from fmr.api.execution_routes import router as execution_router
from fmr.api.financial_data_routes import router as financial_data_router
from fmr.api.input_population_routes import router as input_population_router
from fmr.api.provider_routes import router as provider_router
from fmr.api.write_routes import router as write_router

_LARGE_JSON_PATHS = {
    "/api/v1/financial-data/packages/from-csv",
    "/api/v1/workbooks/executions",
    "/api/v1/workbooks/input-populations",
    "/api/v1/workbooks/calculations",
    "/api/v1/workbooks/calculation-acceptances",
}


def _asset(name: str) -> str:
    return files("fmr.web").joinpath(name).read_text(encoding="utf-8")


def create_app() -> FastAPI:
    application = create_base_app()
    application.include_router(write_router)
    application.include_router(execution_router)
    application.include_router(input_population_router)
    application.include_router(calculation_router)
    application.include_router(financial_data_router)
    application.include_router(provider_router)

    @application.middleware("http")
    async def large_request_limit_override(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.url.path in _LARGE_JSON_PATHS:
            request.scope["headers"] = [
                (name, value)
                for name, value in request.scope.get("headers", [])
                if name.lower() != b"content-length"
            ]
        return await call_next(request)

    @application.get("/assets/realization.js", include_in_schema=False)
    def realization_javascript() -> Response:
        return Response(_asset("realization.js"), media_type="application/javascript")

    @application.get("/assets/write_plan.js", include_in_schema=False)
    def write_plan_javascript() -> Response:
        return Response(_asset("write_plan.js"), media_type="application/javascript")

    @application.get("/assets/execution.js", include_in_schema=False)
    def execution_javascript() -> Response:
        return Response(_asset("execution.js"), media_type="application/javascript")

    @application.get("/assets/input_population.js", include_in_schema=False)
    def input_population_javascript() -> Response:
        return Response(
            _asset("input_population.js"),
            media_type="application/javascript",
        )

    @application.get("/assets/calculation.js", include_in_schema=False)
    def calculation_javascript() -> Response:
        return Response(_asset("calculation.js"), media_type="application/javascript")

    @application.get("/assets/financial_data.js", include_in_schema=False)
    def financial_data_javascript() -> Response:
        return Response(
            _asset("financial_data.js"),
            media_type="application/javascript",
        )

    @application.get("/assets/provider-routing.js", include_in_schema=False)
    def provider_routing_javascript() -> Response:
        return Response(_asset("provider-routing.js"), media_type="application/javascript")

    return application


app = create_app()
