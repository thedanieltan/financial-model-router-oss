from __future__ import annotations

from importlib.resources import files

from fastapi import FastAPI
from fastapi.responses import Response

from fmr.api.app import create_app as create_base_app
from fmr.api.write_routes import router as write_router


def _asset(name: str) -> str:
    return files("fmr.web").joinpath(name).read_text(encoding="utf-8")


def create_app() -> FastAPI:
    application = create_base_app()
    application.include_router(write_router)

    @application.get("/assets/realization.js", include_in_schema=False)
    def realization_javascript() -> Response:
        return Response(_asset("realization.js"), media_type="application/javascript")

    @application.get("/assets/write_plan.js", include_in_schema=False)
    def write_plan_javascript() -> Response:
        return Response(_asset("write_plan.js"), media_type="application/javascript")

    return application


app = create_app()
