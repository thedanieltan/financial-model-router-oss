from __future__ import annotations

from typing import Any

EXECUTION_STATES = ("accepted", "preparing", "blocked", "running", "validating", "completed", "failed", "cancelled")


def validate_execution_result(payload: dict[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    if payload.get("contract_version") != "execution-result.v1":
        issues.append("unsupported contract_version")
    if payload.get("state") not in EXECUTION_STATES:
        issues.append("state is not supported")
    if not isinstance(payload.get("execution_id"), str):
        issues.append("execution_id is required")
    if not isinstance(payload.get("output_artifact_references"), list):
        issues.append("output_artifact_references must be an array")
    forbidden = {"secret", "password", "token", "api_key", "financial_values", "input_values"}
    stack = [payload]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            if forbidden.intersection(key.lower() for key in value):
                issues.append("receipt contains a forbidden sensitive field")
                break
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return tuple(issues)
