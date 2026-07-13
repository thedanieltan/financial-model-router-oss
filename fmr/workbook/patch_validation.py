from __future__ import annotations

from typing import Any

from fmr.workbook.patch import (
    validate_workbook_patch_payload as _validate_patch,
    validate_workbook_patch_receipt_payload as _validate_receipt,
)

_PATCH_FIELDS = {
    "contract_version",
    "patch_id",
    "source",
    "analysis_sha256",
    "transformation_plan_sha256",
    "model_family",
    "ready_for_executor",
    "execution_supported_by_this_release",
    "blockers",
    "preconditions",
    "operations",
    "rollback_plan",
    "output_validation",
    "controls",
}
_OPERATION_FIELDS = {
    "sequence",
    "operation_id",
    "action",
    "source_operation",
    "mode",
    "target",
    "parameters",
    "preconditions",
    "rollback",
    "validations",
}
_RECEIPT_FIELDS = {
    "contract_version",
    "patch_id",
    "source_sha256",
    "output_sha256",
    "status",
    "operation_receipts",
    "validations",
}


def validate_workbook_patch_payload(payload: Any) -> tuple[str, ...]:
    issues = list(_validate_patch(payload))
    if not isinstance(payload, dict):
        return tuple(dict.fromkeys(issues))

    _expect_keys(payload, _PATCH_FIELDS, "patch", issues)
    source = payload.get("source")
    if isinstance(source, dict):
        _expect_keys(source, {"filename", "sha256", "size_bytes"}, "source", issues)
    _validate_check_shapes(payload.get("preconditions"), "preconditions", issues)
    _validate_check_shapes(payload.get("output_validation"), "output_validation", issues)

    operations = payload.get("operations")
    if isinstance(operations, list):
        for index, operation in enumerate(operations):
            if not isinstance(operation, dict):
                continue
            path = f"operations[{index}]"
            _expect_keys(operation, _OPERATION_FIELDS, path, issues)
            target = operation.get("target")
            if isinstance(target, dict):
                _expect_keys(target, {"scope", "semantic_role"}, f"{path}.target", issues)
            parameters = operation.get("parameters")
            if isinstance(parameters, dict):
                _expect_keys(
                    parameters,
                    {"specification_ref", "conflict_policy"},
                    f"{path}.parameters",
                    issues,
                )
            rollback = operation.get("rollback")
            if isinstance(rollback, dict):
                _expect_keys(
                    rollback,
                    {"strategy", "receipt_key", "required_fields"},
                    f"{path}.rollback",
                    issues,
                )
            _validate_check_shapes(
                operation.get("preconditions"),
                f"{path}.preconditions",
                issues,
            )
            _validate_check_shapes(
                operation.get("validations"),
                f"{path}.validations",
                issues,
            )

    rollback_plan = payload.get("rollback_plan")
    if isinstance(rollback_plan, list):
        for index, item in enumerate(rollback_plan):
            if isinstance(item, dict):
                _expect_keys(
                    item,
                    {
                        "sequence",
                        "operation_id",
                        "action",
                        "receipt_key",
                        "required_receipt_fields",
                    },
                    f"rollback_plan[{index}]",
                    issues,
                )
    return tuple(dict.fromkeys(issues))


def validate_workbook_patch_receipt_payload(
    payload: Any,
    *,
    patch: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    strict_patch_issues = validate_workbook_patch_payload(patch) if patch is not None else ()
    issues = list(_validate_receipt(payload, patch=None if strict_patch_issues else patch))
    if strict_patch_issues:
        issues.append("referenced patch is invalid")
    if not isinstance(payload, dict):
        return tuple(dict.fromkeys(issues))

    _expect_keys(payload, _RECEIPT_FIELDS, "receipt", issues)
    operation_receipts = payload.get("operation_receipts")
    if isinstance(operation_receipts, list):
        for index, item in enumerate(operation_receipts):
            if isinstance(item, dict):
                _expect_keys(
                    item,
                    {
                        "operation_id",
                        "status",
                        "before_state_sha256",
                        "after_state_sha256",
                        "rollback_state_sha256",
                        "affected_parts",
                    },
                    f"operation_receipts[{index}]",
                    issues,
                )
    validations = payload.get("validations")
    if isinstance(validations, list):
        for index, item in enumerate(validations):
            if isinstance(item, dict):
                _expect_keys(
                    item,
                    {"check", "passed", "message"},
                    f"validations[{index}]",
                    issues,
                )
    return tuple(dict.fromkeys(issues))


def _validate_check_shapes(value: Any, path: str, issues: list[str]) -> None:
    if not isinstance(value, list):
        return
    for index, item in enumerate(value):
        if isinstance(item, dict):
            _expect_keys(item, {"check", "expected"}, f"{path}[{index}]", issues)


def _expect_keys(
    value: dict[str, Any],
    expected: set[str],
    path: str,
    issues: list[str],
) -> None:
    actual = set(value)
    extra = sorted(actual - expected)
    missing = sorted(expected - actual)
    if extra:
        issues.append(f"{path} contains unsupported fields: {', '.join(extra)}")
    if missing:
        issues.append(f"{path} is missing fields: {', '.join(missing)}")
