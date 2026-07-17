from __future__ import annotations

from importlib.resources import files
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import HTMLResponse, Response

from fmr.practitioner.saas_budget import build_saas_budget_workbook_from_payload

router = APIRouter()


def _asset(name: str) -> str:
    return files("fmr.web").joinpath(name).read_text(encoding="utf-8")


@router.get("/practitioner/saas", response_class=HTMLResponse, include_in_schema=False)
def practitioner_saas_page() -> str:
    return _asset("practitioner_saas.html")


@router.get("/assets/practitioner_saas.js", include_in_schema=False)
def practitioner_saas_javascript() -> Response:
    return Response(_asset("practitioner_saas.js"), media_type="application/javascript")


@router.post("/api/v1/practitioner/saas-budget-forecast", include_in_schema=True)
def generate_saas_budget_workbook(payload: dict[str, Any] = Body(...)) -> Response:
    try:
        workbook = build_saas_budget_workbook_from_payload(payload)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_saas_budget_request", "message": str(exc)}) from exc
    filename = "saas-budget-forecast.xlsx"
    return Response(
        workbook,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
