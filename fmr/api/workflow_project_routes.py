from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fmr.workflow_projects import DEFAULT_WORKFLOW_PROJECT_STORE


class WorkflowProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    plan: dict[str, Any]


class WorkflowProjectApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: dict[str, bool]
    expected_version: int | None = Field(default=None, ge=1)


class WorkflowProjectExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int | None = Field(default=None, ge=1)


router = APIRouter(prefix="/api/v2/workflow-projects", tags=["workflow projects"])


@router.get("")
def list_workflow_projects() -> dict[str, Any]:
    return DEFAULT_WORKFLOW_PROJECT_STORE.list()


@router.post("")
def create_workflow_project(
    payload: WorkflowProjectCreateRequest,
) -> dict[str, Any]:
    try:
        return DEFAULT_WORKFLOW_PROJECT_STORE.create(payload.name, payload.plan)
    except ValueError as exc:
        raise _invalid(exc) from exc
    except RuntimeError as exc:
        raise _conflict(exc) from exc


@router.get("/{project_id}")
def get_workflow_project(project_id: str) -> dict[str, Any]:
    try:
        return DEFAULT_WORKFLOW_PROJECT_STORE.get(project_id)
    except ValueError as exc:
        raise _invalid(exc) from exc
    except KeyError as exc:
        raise _not_found(exc) from exc


@router.get("/{project_id}/events")
def get_workflow_project_events(project_id: str) -> dict[str, Any]:
    try:
        return DEFAULT_WORKFLOW_PROJECT_STORE.events(project_id)
    except ValueError as exc:
        raise _invalid(exc) from exc
    except KeyError as exc:
        raise _not_found(exc) from exc


@router.post("/{project_id}/approvals")
def approve_workflow_project(
    project_id: str,
    payload: WorkflowProjectApprovalRequest,
) -> dict[str, Any]:
    try:
        return DEFAULT_WORKFLOW_PROJECT_STORE.set_approvals(
            project_id,
            payload.decisions,
            expected_version=payload.expected_version,
        )
    except ValueError as exc:
        raise _invalid(exc) from exc
    except KeyError as exc:
        raise _not_found(exc) from exc
    except RuntimeError as exc:
        raise _conflict(exc) from exc


@router.post("/{project_id}/executions")
def execute_workflow_project(
    project_id: str,
    payload: WorkflowProjectExecutionRequest,
) -> dict[str, Any]:
    try:
        return DEFAULT_WORKFLOW_PROJECT_STORE.execute(
            project_id,
            expected_version=payload.expected_version,
        )
    except ValueError as exc:
        raise _invalid(exc) from exc
    except KeyError as exc:
        raise _not_found(exc) from exc
    except RuntimeError as exc:
        raise _conflict(exc) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "workflow_project_execution_failed", "message": str(exc)},
        ) from exc


def _invalid(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"code": "workflow_project_invalid", "message": str(exc)},
    )


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "workflow_project_not_found", "message": str(exc)},
    )


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": "workflow_project_conflict", "message": str(exc)},
    )


__all__ = ["router"]
