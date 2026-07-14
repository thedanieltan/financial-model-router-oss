from __future__ import annotations

import hashlib
import json
import re
import string
from dataclasses import dataclass
from typing import Any

from fmr.providers.native_xlsx.workbook.analyse import WorkbookAnalysis

_PATCH_ID_RE = re.compile(r"^fmrp_[0-9a-f]{24}$")
_OPERATION_ID_RE = re.compile(r"^op-[0-9]{3}$")
_FORBIDDEN_KEYS = {
    "cell",
    "cell_write",
    "formula",
    "macro",
    "script",
    "vba",
    "workbook_bytes",
}
_ALLOWED_ACTIONS = {
    "add_control",
    "add_scenario",
    "add_sensitivity",
    "append_periods",
    "ensure_section",
    "ensure_sheet",
    "link_components",
}
_ALLOWED_PRECONDITIONS = {
    "analysis_digest_matches",
    "source_extension_is_xlsx",
    "source_filename_matches",
    "source_hash_matches",
    "source_remains_unmodified",
    "source_size_matches",
    "transformation_plan_digest_matches",
}
_ALLOWED_OUTPUT_VALIDATIONS = {
    "external_link_state_preserved",
    "operation_postconditions_pass",
    "output_archive_is_safe",
    "output_is_distinct_file",
    "output_reopens_as_xlsx",
    "source_hash_unchanged",
}
_ALLOWED_CONTROLS = {
    "additive_operations_only",
    "approved_operations_only",
    "do_not_execute_macros",
    "do_not_overwrite_source_workbook",
    "executor_not_included",
    "formulas_require_separate_specification",
}
_OPERATION_SPECS: dict[str, tuple[str, str]] = {
    "create_assumptions_section": ("ensure_sheet", "assumptions"),
    "add_forecast_periods": ("append_periods", "forecast_periods"),
    "create_revenue_schedule": ("ensure_sheet", "revenue_schedule"),
    "create_operating_cost_schedule": ("ensure_sheet", "operating_cost_schedule"),
    "create_working_capital_schedule": ("ensure_sheet", "working_capital_schedule"),
    "create_capital_expenditure_schedule": (
        "ensure_sheet",
        "capital_expenditure_schedule",
    ),
    "create_debt_schedule": ("ensure_sheet", "debt_schedule"),
    "create_interest_schedule": ("ensure_sheet", "interest_schedule"),
    "create_cash_sweep_schedule": ("ensure_sheet", "cash_sweep_schedule"),
    "create_covenant_schedule": ("ensure_sheet", "covenant_schedule"),
    "create_refinancing_scenarios": ("add_scenario", "refinancing"),
    "link_financial_statements": ("link_components", "financial_statements"),
    "extend_operating_forecast": ("append_periods", "operating_forecast"),
    "create_free_cash_flow_schedule": ("ensure_sheet", "free_cash_flow_schedule"),
    "create_discount_factor_schedule": ("ensure_sheet", "discount_factor_schedule"),
    "create_terminal_value_section": ("ensure_section", "terminal_value"),
    "create_enterprise_to_equity_bridge": (
        "ensure_section",
        "enterprise_to_equity_bridge",
    ),
    "add_valuation_sensitivity": ("add_sensitivity", "valuation"),
    "add_integrity_checks": ("add_control", "integrity"),
    "add_balance_checks": ("add_control", "balance"),
    "add_cash_flow_checks": ("add_control", "cash_flow"),
    "add_liquidity_checks": ("add_control", "liquidity"),
}


@dataclass(frozen=True)
class PatchCheck:
    check: str
    expected: str | int | bool

    def to_dict(self) -> dict[str, Any]:
        return {"check": self.check, "expected": self.expected}


@dataclass(frozen=True)
class PatchOperation:
    sequence: int
    operation_id: str
    action: str
    source_operation: str
    semantic_role: str
    preconditions: tuple[PatchCheck, ...]
    validations: tuple[PatchCheck, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "operation_id": self.operation_id,
            "action": self.action,
            "source_operation": self.source_operation,
            "mode": "additive",
            "target": {
                "scope": "workbook",
                "semantic_role": self.semantic_role,
            },
            "parameters": {
                "specification_ref": (
                    f"fmr://workbook-operations/{self.source_operation}/v1"
                ),
                "conflict_policy": "reuse_matching_or_fail",
            },
            "preconditions": [item.to_dict() for item in self.preconditions],
            "rollback": {
                "strategy": "operation_receipt",
                "receipt_key": f"operations.{self.operation_id}",
                "required_fields": [
                    "before_state_sha256",
                    "after_state_sha256",
                    "affected_parts",
                ],
            },
            "validations": [item.to_dict() for item in self.validations],
        }


@dataclass(frozen=True)
class WorkbookPatch:
    patch_id: str
    source_filename: str
    source_sha256: str
    source_size_bytes: int
    analysis_sha256: str
    transformation_plan_sha256: str
    model_family: str
    ready_for_executor: bool
    execution_supported_by_this_release: bool
    blockers: tuple[str, ...]
    preconditions: tuple[PatchCheck, ...]
    operations: tuple[PatchOperation, ...]
    rollback_plan: tuple[dict[str, Any], ...]
    output_validation: tuple[PatchCheck, ...]
    controls: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": "workbook-patch.v1",
            "patch_id": self.patch_id,
            "source": {
                "filename": self.source_filename,
                "sha256": self.source_sha256,
                "size_bytes": self.source_size_bytes,
            },
            "analysis_sha256": self.analysis_sha256,
            "transformation_plan_sha256": self.transformation_plan_sha256,
            "model_family": self.model_family,
            "ready_for_executor": self.ready_for_executor,
            "execution_supported_by_this_release": (
                self.execution_supported_by_this_release
            ),
            "blockers": list(self.blockers),
            "preconditions": [item.to_dict() for item in self.preconditions],
            "operations": [item.to_dict() for item in self.operations],
            "rollback_plan": list(self.rollback_plan),
            "output_validation": [
                item.to_dict() for item in self.output_validation
            ],
            "controls": list(self.controls),
        }


def compile_workbook_patch(analysis: WorkbookAnalysis) -> WorkbookPatch:
    analysis_payload = analysis.to_dict()
    analysis_sha256 = _digest(analysis_payload)
    plan_payload = analysis.transformation_plan.to_dict()
    plan_sha256 = _digest(plan_payload)
    blockers: list[str] = []

    if not analysis.transformation_plan.ready_to_apply:
        blockers.extend(
            f"analysis_not_ready:{item}"
            for item in analysis.transformation_plan.unresolved_inputs
        )
    if analysis.workbook_map.external_links_detected:
        blockers.append("external_links_detected")
    blockers.extend(
        finding
        for finding in analysis.workbook_map.findings
        if finding.startswith("unsupported_sheet_type:")
    )

    operations: list[PatchOperation] = []
    for source in analysis.transformation_plan.operations:
        if source.operation in {"preserve_existing_workbook", "request_missing_inputs"}:
            continue
        spec = _OPERATION_SPECS.get(source.operation)
        if spec is None:
            blockers.append(f"unmapped_operation:{source.operation}")
            continue
        action, semantic_role = spec
        operation_id = f"op-{len(operations) + 1:03d}"
        operations.append(
            PatchOperation(
                sequence=len(operations) + 1,
                operation_id=operation_id,
                action=action,
                source_operation=source.operation,
                semantic_role=semantic_role,
                preconditions=(
                    PatchCheck("target_is_unambiguous", True),
                    PatchCheck("source_operation_is_approved", True),
                ),
                validations=(
                    PatchCheck("operation_postcondition_passes", True),
                ),
            )
        )
    if not operations:
        blockers.append("no_patch_operations")

    preconditions = (
        PatchCheck("source_hash_matches", analysis.workbook_map.source_sha256),
        PatchCheck("source_size_matches", analysis.workbook_map.source_size_bytes),
        PatchCheck("source_filename_matches", analysis.workbook_map.source_filename),
        PatchCheck("source_extension_is_xlsx", True),
        PatchCheck("source_remains_unmodified", True),
        PatchCheck("analysis_digest_matches", analysis_sha256),
        PatchCheck("transformation_plan_digest_matches", plan_sha256),
    )
    rollback_plan = tuple(
        {
            "sequence": index,
            "operation_id": operation.operation_id,
            "action": "restore_operation_receipt",
            "receipt_key": f"operations.{operation.operation_id}",
            "required_receipt_fields": [
                "before_state_sha256",
                "after_state_sha256",
                "affected_parts",
            ],
        }
        for index, operation in enumerate(reversed(operations), start=1)
    )
    output_validation = (
        PatchCheck("output_is_distinct_file", True),
        PatchCheck("source_hash_unchanged", analysis.workbook_map.source_sha256),
        PatchCheck("output_reopens_as_xlsx", True),
        PatchCheck("output_archive_is_safe", True),
        PatchCheck("operation_postconditions_pass", True),
        PatchCheck(
            "external_link_state_preserved",
            analysis.workbook_map.external_links_detected,
        ),
    )
    controls = (
        "do_not_overwrite_source_workbook",
        "do_not_execute_macros",
        "approved_operations_only",
        "additive_operations_only",
        "formulas_require_separate_specification",
        "executor_not_included",
    )
    deduplicated_blockers = tuple(dict.fromkeys(blockers))
    provisional = {
        "contract_version": "workbook-patch.v1",
        "source": {
            "filename": analysis.workbook_map.source_filename,
            "sha256": analysis.workbook_map.source_sha256,
            "size_bytes": analysis.workbook_map.source_size_bytes,
        },
        "analysis_sha256": analysis_sha256,
        "transformation_plan_sha256": plan_sha256,
        "model_family": analysis.recommendation.model_family,
        "ready_for_executor": not deduplicated_blockers,
        "execution_supported_by_this_release": False,
        "blockers": list(deduplicated_blockers),
        "preconditions": [item.to_dict() for item in preconditions],
        "operations": [item.to_dict() for item in operations],
        "rollback_plan": list(rollback_plan),
        "output_validation": [item.to_dict() for item in output_validation],
        "controls": list(controls),
    }
    patch_id = f"fmrp_{_digest(provisional)[:24]}"
    return WorkbookPatch(
        patch_id=patch_id,
        source_filename=analysis.workbook_map.source_filename,
        source_sha256=analysis.workbook_map.source_sha256,
        source_size_bytes=analysis.workbook_map.source_size_bytes,
        analysis_sha256=analysis_sha256,
        transformation_plan_sha256=plan_sha256,
        model_family=analysis.recommendation.model_family,
        ready_for_executor=not deduplicated_blockers,
        execution_supported_by_this_release=False,
        blockers=deduplicated_blockers,
        preconditions=preconditions,
        operations=tuple(operations),
        rollback_plan=rollback_plan,
        output_validation=output_validation,
        controls=controls,
    )


def validate_workbook_patch_payload(payload: Any) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("patch must be an object",)
    if payload.get("contract_version") != "workbook-patch.v1":
        issues.append("unsupported contract_version")
    if _contains_forbidden_key(payload):
        issues.append("patch contains executable workbook fields")

    patch_id = payload.get("patch_id")
    if not isinstance(patch_id, str) or not _PATCH_ID_RE.fullmatch(patch_id):
        issues.append("patch_id is invalid")
    source = payload.get("source")
    if not isinstance(source, dict):
        issues.append("source must be an object")
    else:
        _validate_source(source, issues)
    for field in ("analysis_sha256", "transformation_plan_sha256"):
        if not _is_sha256(payload.get(field)):
            issues.append(f"{field} must be a SHA-256 hex string")
    if not isinstance(payload.get("model_family"), str) or not payload.get(
        "model_family"
    ):
        issues.append("model_family must be a non-empty string")
    for field in ("ready_for_executor", "execution_supported_by_this_release"):
        if not isinstance(payload.get(field), bool):
            issues.append(f"{field} must be boolean")
    if payload.get("execution_supported_by_this_release") is not False:
        issues.append(
            "execution_supported_by_this_release must be false for this release"
        )

    blockers = payload.get("blockers")
    if not _is_string_list(blockers):
        issues.append("blockers must be an array of strings")
    elif payload.get("ready_for_executor") is not (len(blockers) == 0):
        issues.append("ready_for_executor does not match blockers")

    _validate_checks(
        payload.get("preconditions"),
        "preconditions",
        _ALLOWED_PRECONDITIONS,
        issues,
        require_exact=True,
    )
    precondition_map = _check_map(payload.get("preconditions"))
    if isinstance(source, dict):
        expected_preconditions = {
            "source_hash_matches": source.get("sha256"),
            "source_size_matches": source.get("size_bytes"),
            "source_filename_matches": source.get("filename"),
            "source_extension_is_xlsx": True,
            "source_remains_unmodified": True,
            "analysis_digest_matches": payload.get("analysis_sha256"),
            "transformation_plan_digest_matches": payload.get(
                "transformation_plan_sha256"
            ),
        }
        if precondition_map != expected_preconditions:
            issues.append("preconditions do not match patch metadata")

    operations = payload.get("operations")
    operation_ids: list[str] = []
    if not isinstance(operations, list):
        issues.append("operations must be an array")
    else:
        for index, operation in enumerate(operations):
            path = f"operations[{index}]"
            if not isinstance(operation, dict):
                issues.append(f"{path} must be an object")
                continue
            expected_sequence = index + 1
            if operation.get("sequence") != expected_sequence:
                issues.append(f"{path}.sequence must equal {expected_sequence}")
            operation_id = operation.get("operation_id")
            expected_id = f"op-{expected_sequence:03d}"
            if operation_id != expected_id:
                issues.append(f"{path}.operation_id must equal {expected_id}")
            else:
                operation_ids.append(operation_id)
            source_operation = operation.get("source_operation")
            spec = _OPERATION_SPECS.get(source_operation)
            if spec is None:
                issues.append(f"{path}.source_operation is not approved")
            if operation.get("action") not in _ALLOWED_ACTIONS:
                issues.append(f"{path}.action is not allowed")
            elif spec is not None and operation.get("action") != spec[0]:
                issues.append(f"{path}.action does not match source_operation")
            if operation.get("mode") != "additive":
                issues.append(f"{path}.mode must be additive")
            target = operation.get("target")
            if not isinstance(target, dict):
                issues.append(f"{path}.target must be an object")
            elif (
                target.get("scope") != "workbook"
                or not isinstance(target.get("semantic_role"), str)
                or not target.get("semantic_role")
            ):
                issues.append(f"{path}.target is invalid")
            elif spec is not None and target.get("semantic_role") != spec[1]:
                issues.append(f"{path}.target does not match source_operation")
            parameters = operation.get("parameters")
            if not isinstance(parameters, dict):
                issues.append(f"{path}.parameters must be an object")
            else:
                expected_ref = (
                    f"fmr://workbook-operations/{source_operation}/v1"
                    if isinstance(source_operation, str)
                    else None
                )
                if parameters.get("specification_ref") != expected_ref:
                    issues.append(f"{path}.parameters.specification_ref is invalid")
                if parameters.get("conflict_policy") != "reuse_matching_or_fail":
                    issues.append(f"{path}.parameters.conflict_policy is invalid")
            _validate_checks(
                operation.get("preconditions"),
                f"{path}.preconditions",
                {"target_is_unambiguous", "source_operation_is_approved"},
                issues,
                require_exact=True,
            )
            if _check_map(operation.get("preconditions")) != {
                "target_is_unambiguous": True,
                "source_operation_is_approved": True,
            }:
                issues.append(f"{path}.preconditions are invalid")
            _validate_checks(
                operation.get("validations"),
                f"{path}.validations",
                {"operation_postcondition_passes"},
                issues,
                require_exact=True,
            )
            if _check_map(operation.get("validations")) != {
                "operation_postcondition_passes": True
            }:
                issues.append(f"{path}.validations are invalid")
            rollback = operation.get("rollback")
            if not isinstance(rollback, dict):
                issues.append(f"{path}.rollback must be an object")
            elif (
                rollback.get("strategy") != "operation_receipt"
                or rollback.get("receipt_key") != f"operations.{operation_id}"
                or rollback.get("required_fields")
                != [
                    "before_state_sha256",
                    "after_state_sha256",
                    "affected_parts",
                ]
            ):
                issues.append(f"{path}.rollback is invalid")
    if not operations:
        issues.append("operations must not be empty")

    rollback_plan = payload.get("rollback_plan")
    if not isinstance(rollback_plan, list):
        issues.append("rollback_plan must be an array")
    else:
        expected_ids = list(reversed(operation_ids))
        actual_ids: list[str] = []
        for index, item in enumerate(rollback_plan):
            path = f"rollback_plan[{index}]"
            if not isinstance(item, dict):
                issues.append(f"{path} must be an object")
                continue
            if item.get("sequence") != index + 1:
                issues.append(f"{path}.sequence must equal {index + 1}")
            operation_id = item.get("operation_id")
            actual_ids.append(operation_id)
            if (
                item.get("action") != "restore_operation_receipt"
                or item.get("receipt_key") != f"operations.{operation_id}"
                or item.get("required_receipt_fields")
                != [
                    "before_state_sha256",
                    "after_state_sha256",
                    "affected_parts",
                ]
            ):
                issues.append(f"{path} is invalid")
        if actual_ids != expected_ids:
            issues.append("rollback_plan must reverse operation order")

    _validate_checks(
        payload.get("output_validation"),
        "output_validation",
        _ALLOWED_OUTPUT_VALIDATIONS,
        issues,
        require_exact=True,
    )
    output_map = _check_map(payload.get("output_validation"))
    if isinstance(source, dict):
        expected_output = {
            "output_is_distinct_file": True,
            "source_hash_unchanged": source.get("sha256"),
            "output_reopens_as_xlsx": True,
            "output_archive_is_safe": True,
            "operation_postconditions_pass": True,
            "external_link_state_preserved": output_map.get(
                "external_link_state_preserved"
            ),
        }
        if output_map != expected_output:
            issues.append("output_validation does not match required checks")
    controls = payload.get("controls")
    if not _is_string_list(controls):
        issues.append("controls must be an array of strings")
    elif set(controls) != _ALLOWED_CONTROLS or len(controls) != len(
        _ALLOWED_CONTROLS
    ):
        issues.append("controls do not match the required control set")

    if isinstance(patch_id, str) and _PATCH_ID_RE.fullmatch(patch_id):
        candidate = dict(payload)
        candidate.pop("patch_id", None)
        expected_patch_id = f"fmrp_{_digest(candidate)[:24]}"
        if patch_id != expected_patch_id:
            issues.append("patch_id does not match payload")

    return tuple(dict.fromkeys(issues))


def validate_workbook_patch_receipt_payload(
    payload: Any,
    *,
    patch: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("receipt must be an object",)
    if payload.get("contract_version") != "workbook-patch-receipt.v1":
        issues.append("unsupported contract_version")
    if _contains_forbidden_key(payload):
        issues.append("receipt contains executable workbook fields")
    patch_id = payload.get("patch_id")
    if not isinstance(patch_id, str) or not _PATCH_ID_RE.fullmatch(patch_id):
        issues.append("patch_id is invalid")
    if not _is_sha256(payload.get("source_sha256")):
        issues.append("source_sha256 must be a SHA-256 hex string")
    output_sha = payload.get("output_sha256")
    if output_sha is not None and not _is_sha256(output_sha):
        issues.append("output_sha256 must be null or a SHA-256 hex string")
    status = payload.get("status")
    if status not in {"applied", "failed", "rolled_back"}:
        issues.append("status is invalid")
    if status == "applied" and output_sha is None:
        issues.append("applied receipts require output_sha256")

    receipts = payload.get("operation_receipts")
    receipt_ids: list[str] = []
    if not isinstance(receipts, list):
        issues.append("operation_receipts must be an array")
    else:
        for index, receipt in enumerate(receipts):
            path = f"operation_receipts[{index}]"
            if not isinstance(receipt, dict):
                issues.append(f"{path} must be an object")
                continue
            operation_id = receipt.get("operation_id")
            if not isinstance(operation_id, str) or not _OPERATION_ID_RE.fullmatch(
                operation_id
            ):
                issues.append(f"{path}.operation_id is invalid")
            elif operation_id in receipt_ids:
                issues.append(f"{path}.operation_id is duplicated")
            else:
                receipt_ids.append(operation_id)
            if receipt.get("status") not in {
                "applied",
                "failed",
                "rolled_back",
                "skipped",
            }:
                issues.append(f"{path}.status is invalid")
            for field in ("before_state_sha256", "after_state_sha256"):
                if not _is_sha256(receipt.get(field)):
                    issues.append(f"{path}.{field} must be a SHA-256 hex string")
            rollback_sha = receipt.get("rollback_state_sha256")
            if rollback_sha is not None and not _is_sha256(rollback_sha):
                issues.append(
                    f"{path}.rollback_state_sha256 must be null or a SHA-256 hex string"
                )
            if not _is_string_list(receipt.get("affected_parts")):
                issues.append(f"{path}.affected_parts must be an array of strings")

    validations = payload.get("validations")
    if not isinstance(validations, list):
        issues.append("validations must be an array")
    else:
        for index, validation in enumerate(validations):
            path = f"validations[{index}]"
            if not isinstance(validation, dict):
                issues.append(f"{path} must be an object")
                continue
            if not isinstance(validation.get("check"), str) or not validation.get(
                "check"
            ):
                issues.append(f"{path}.check must be a non-empty string")
            if not isinstance(validation.get("passed"), bool):
                issues.append(f"{path}.passed must be boolean")
            if not isinstance(validation.get("message"), str):
                issues.append(f"{path}.message must be a string")

    if patch is not None:
        patch_issues = validate_workbook_patch_payload(patch)
        if patch_issues:
            issues.append("referenced patch is invalid")
        else:
            if patch_id != patch.get("patch_id"):
                issues.append("receipt patch_id does not match patch")
            source = patch.get("source", {})
            if payload.get("source_sha256") != source.get("sha256"):
                issues.append("receipt source_sha256 does not match patch")
            expected_ids = [
                item["operation_id"] for item in patch.get("operations", [])
            ]
            if receipt_ids != expected_ids:
                issues.append("operation_receipts do not match patch operations")
    return tuple(dict.fromkeys(issues))


def _validate_source(source: dict[str, Any], issues: list[str]) -> None:
    if not isinstance(source.get("filename"), str) or not source.get("filename"):
        issues.append("source.filename must be a non-empty string")
    elif not source["filename"].lower().endswith(".xlsx"):
        issues.append("source.filename must end with .xlsx")
    if not _is_sha256(source.get("sha256")):
        issues.append("source.sha256 must be a SHA-256 hex string")
    if not isinstance(source.get("size_bytes"), int) or source.get("size_bytes") < 0:
        issues.append("source.size_bytes must be a non-negative integer")


def _validate_checks(
    value: Any,
    path: str,
    allowed: set[str],
    issues: list[str],
    *,
    require_exact: bool = False,
) -> None:
    if not isinstance(value, list):
        issues.append(f"{path} must be an array")
        return
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            issues.append(f"{item_path} must be an object")
            continue
        check = item.get("check")
        if check not in allowed:
            issues.append(f"{item_path}.check is not allowed")
        elif check in seen:
            issues.append(f"{item_path}.check is duplicated")
        else:
            seen.add(check)
        if not isinstance(item.get("expected"), (str, int, bool)):
            issues.append(f"{item_path}.expected has an invalid type")
    if require_exact and seen != allowed:
        issues.append(f"{path} does not contain the required check set")


def _check_map(value: Any) -> dict[str, str | int | bool]:
    if not isinstance(value, list):
        return {}
    result: dict[str, str | int | bool] = {}
    for item in value:
        if (
            isinstance(item, dict)
            and isinstance(item.get("check"), str)
            and isinstance(item.get("expected"), (str, int, bool))
        ):
            result[item["check"]] = item["expected"]
    return result


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                return True
            if _contains_forbidden_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in string.hexdigits for character in value)
    )


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
