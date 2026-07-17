from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from fmr.workflow import execute_workflow, validate_workflow_plan


_DISPLAY_TOKEN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("project name must be a non-empty string")
    cleaned = " ".join(value.split())
    if len(cleaned) > 160:
        raise ValueError("project name must not exceed 160 characters")
    if "<" in cleaned or ">" in cleaned:
        raise ValueError("project name contains unsupported markup characters")
    return cleaned


def _validate_display_fields(plan: dict[str, Any]) -> None:
    for step in plan["steps"]:
        for field in ("step_id", "capability"):
            value = step[field]
            if not isinstance(value, str) or not _DISPLAY_TOKEN.fullmatch(value):
                raise ValueError(
                    f"workflow project {field} must use lowercase underscore tokens"
                )


def _decisions(value: Any, *, allowed: set[str]) -> dict[str, bool]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and key and isinstance(decision, bool)
        for key, decision in value.items()
    ):
        raise ValueError("approval decisions must be an object of boolean values")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError("approval decisions contain unknown gates: " + ",".join(unknown))
    return {key: value[key] for key in sorted(value)}


def _normalize_project_execution(
    plan: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    """Report an approval wait ahead of derivative dependency blocks."""
    if result["state"] != "blocked":
        return result
    mandatory = {
        step["step_id"] for step in plan["steps"] if step["mandatory"]
    }
    if not any(
        step["step_id"] in mandatory and step["state"] == "awaiting_approval"
        for step in result["step_results"]
    ):
        return result
    provisional = {
        key: value
        for key, value in result.items()
        if key != "workflow_execution_id"
    }
    provisional["state"] = "awaiting_approval"
    return {
        **provisional,
        "workflow_execution_id": f"fmrwx_{_digest(provisional)[:24]}",
    }


class WorkflowProjectStore:
    """Persist value-free workflow plans, decisions and execution receipts locally."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        output_root: str | Path | None = None,
    ) -> None:
        base = Path.home() / ".fmr"
        self.path = Path(path or base / "workflow-projects.sqlite3").resolve()
        self.output_root = Path(
            output_root or base / "workflow-project-outputs"
        ).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS workflow_projects_v1 ("
                "project_id TEXT PRIMARY KEY, name TEXT NOT NULL, workflow_id TEXT NOT NULL, "
                "workflow_sha256 TEXT NOT NULL, plan_json TEXT NOT NULL, approvals_json TEXT NOT NULL, "
                "latest_execution_json TEXT, status TEXT NOT NULL, version INTEGER NOT NULL, "
                "created_at REAL NOT NULL, updated_at REAL NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS workflow_projects_updated_v1 "
                "ON workflow_projects_v1(updated_at DESC, project_id)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS workflow_project_events_v1 ("
                "event_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, "
                "project_version INTEGER NOT NULL, event_type TEXT NOT NULL, occurred_at REAL NOT NULL, "
                "detail_code TEXT NOT NULL, FOREIGN KEY(project_id) REFERENCES workflow_projects_v1(project_id))"
            )

    def create(self, name: str, plan: dict[str, Any]) -> dict[str, Any]:
        issues = validate_workflow_plan(plan)
        if issues:
            raise ValueError("invalid workflow plan: " + "; ".join(issues))
        _validate_display_fields(plan)
        project_name = _name(name)
        seed = {
            "name": project_name,
            "workflow_sha256": plan["workflow_sha256"],
        }
        project_id = f"fmrprj_{_digest(seed)[:24]}"
        plan_json = json.dumps(plan, sort_keys=True, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT plan_json, name FROM workflow_projects_v1 WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if row is not None:
                if row[0] != plan_json or row[1] != project_name:
                    raise RuntimeError("existing workflow project identity does not match")
                return self._read(connection, project_id)
            now = time.time()
            status = "blocked" if plan["status"] == "blocked" else "planned"
            connection.execute(
                "INSERT INTO workflow_projects_v1("
                "project_id, name, workflow_id, workflow_sha256, plan_json, approvals_json, "
                "latest_execution_json, status, version, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, '{}', NULL, ?, 1, ?, ?)",
                (
                    project_id,
                    project_name,
                    plan["workflow_id"],
                    plan["workflow_sha256"],
                    plan_json,
                    status,
                    now,
                    now,
                ),
            )
            self._event(connection, project_id, 1, "created", "plan_saved", now)
            return self._read(connection, project_id)

    def get(self, project_id: str) -> dict[str, Any]:
        identifier = self._project_id(project_id)
        with self._connect() as connection:
            return self._read(connection, identifier)

    def list(self) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT project_id, name, workflow_id, workflow_sha256, status, version, "
                "created_at, updated_at, latest_execution_json "
                "FROM workflow_projects_v1 ORDER BY updated_at DESC, project_id"
            ).fetchall()
        projects = []
        for row in rows:
            latest = json.loads(row[8]) if row[8] else None
            projects.append(
                {
                    "project_id": row[0],
                    "name": row[1],
                    "workflow_id": row[2],
                    "workflow_sha256": row[3],
                    "status": row[4],
                    "version": row[5],
                    "created_at": row[6],
                    "updated_at": row[7],
                    "latest_execution_id": latest.get("workflow_execution_id") if latest else None,
                }
            )
        return {
            "contract_version": "workflow-project-list.v1",
            "projects": projects,
        }

    def set_approvals(
        self,
        project_id: str,
        decisions: dict[str, bool],
        *,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        identifier = self._project_id(project_id)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            project = self._read(connection, identifier)
            self._check_version(project, expected_version)
            gate_ids = {
                step["step_id"]
                for step in project["plan"]["steps"]
                if step["kind"] == "human_gate"
            }
            approved = _decisions(decisions, allowed=gate_ids)
            merged = {**project["approvals"], **approved}
            version = project["version"] + 1
            now = time.time()
            connection.execute(
                "UPDATE workflow_projects_v1 SET approvals_json = ?, status = ?, "
                "version = ?, updated_at = ? WHERE project_id = ?",
                (
                    json.dumps(merged, sort_keys=True, separators=(",", ":")),
                    "approval_recorded",
                    version,
                    now,
                    identifier,
                ),
            )
            detail = "approval_rejected" if any(value is False for value in approved.values()) else "approval_recorded"
            self._event(connection, identifier, version, "approval", detail, now)
            return self._read(connection, identifier)

    def execute(
        self,
        project_id: str,
        *,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        identifier = self._project_id(project_id)
        with self._connect() as connection:
            project = self._read(connection, identifier)
            self._check_version(project, expected_version)
        result = _normalize_project_execution(
            project["plan"],
            execute_workflow(
                project["plan"],
                idempotency_key=f"{identifier}:{project['workflow_sha256']}",
                output_dir=self.output_root / identifier,
                approvals=project["approvals"],
            ),
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._read(connection, identifier)
            self._check_version(current, project["version"])
            version = current["version"] + 1
            now = time.time()
            connection.execute(
                "UPDATE workflow_projects_v1 SET latest_execution_json = ?, status = ?, "
                "version = ?, updated_at = ? WHERE project_id = ?",
                (
                    json.dumps(result, sort_keys=True, separators=(",", ":")),
                    result["state"],
                    version,
                    now,
                    identifier,
                ),
            )
            self._event(
                connection,
                identifier,
                version,
                "execution",
                f"execution_{result['state']}",
                now,
            )
            return self._read(connection, identifier)

    def events(self, project_id: str) -> dict[str, Any]:
        identifier = self._project_id(project_id)
        with self._connect() as connection:
            self._read(connection, identifier)
            rows = connection.execute(
                "SELECT project_version, event_type, occurred_at, detail_code "
                "FROM workflow_project_events_v1 WHERE project_id = ? ORDER BY event_id",
                (identifier,),
            ).fetchall()
        return {
            "contract_version": "workflow-project-events.v1",
            "project_id": identifier,
            "events": [
                {
                    "project_version": row[0],
                    "event_type": row[1],
                    "occurred_at": row[2],
                    "detail_code": row[3],
                }
                for row in rows
            ],
        }

    @staticmethod
    def _check_version(project: dict[str, Any], expected: int | None) -> None:
        if expected is not None and project["version"] != expected:
            raise RuntimeError("workflow project version conflict")

    @staticmethod
    def _project_id(value: Any) -> str:
        if not isinstance(value, str) or not value.startswith("fmrprj_") or len(value) != 31:
            raise ValueError("workflow project id is invalid")
        return value

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        project_id: str,
        version: int,
        event_type: str,
        detail_code: str,
        occurred_at: float,
    ) -> None:
        connection.execute(
            "INSERT INTO workflow_project_events_v1("
            "project_id, project_version, event_type, occurred_at, detail_code) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, version, event_type, occurred_at, detail_code),
        )

    @staticmethod
    def _read(connection: sqlite3.Connection, project_id: str) -> dict[str, Any]:
        row = connection.execute(
            "SELECT project_id, name, workflow_id, workflow_sha256, plan_json, approvals_json, "
            "latest_execution_json, status, version, created_at, updated_at "
            "FROM workflow_projects_v1 WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            raise KeyError("workflow project was not found")
        return {
            "contract_version": "workflow-project.v1",
            "project_id": row[0],
            "name": row[1],
            "workflow_id": row[2],
            "workflow_sha256": row[3],
            "plan": json.loads(row[4]),
            "approvals": json.loads(row[5]),
            "latest_execution": json.loads(row[6]) if row[6] else None,
            "status": row[7],
            "version": row[8],
            "created_at": row[9],
            "updated_at": row[10],
        }

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection


DEFAULT_WORKFLOW_PROJECT_STORE = WorkflowProjectStore()


__all__ = ["DEFAULT_WORKFLOW_PROJECT_STORE", "WorkflowProjectStore"]
