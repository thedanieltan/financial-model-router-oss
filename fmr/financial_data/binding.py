from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from decimal import Decimal
from typing import Any

from fmr.financial_data.common import (
    ALLOWED_SELECTORS,
    BINDING_CONTROLS,
    BINDING_PLAN_ID_RE,
    BINDING_PROFILE_ID_RE,
    CONCEPTS,
    digest,
    json_number,
    valid_value,
)
from fmr.financial_data.mapping import validate_mapping_result
from fmr.financial_data.package import validate_financial_data_package
from fmr.workbook.executor_public import validate_workbook_execution_receipt_payload
from fmr.workbook.input_population import validate_workbook_input_set_payload
from fmr.workbook.write_plan_public import validate_workbook_write_plan_payload

_RANGE_RE = re.compile(
    r"^([A-Z]{1,3})([1-9][0-9]*)(?::([A-Z]{1,3})([1-9][0-9]*))?$"
)
_INPUT_SET_CONTROLS = [
    "complete_reserved_input_coverage",
    "execution_receipt_pinned",
    "explicit_record_binding",
    "finite_values_only",
    "formulas_forbidden",
    "source_provenance_declared",
    "write_plan_pinned",
]


def build_binding_profile(
    bindings: list[dict[str, Any]],
    *,
    name: str = "binding profile",
) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            raise ValueError(f"binding {index} must be an object")
        source_type = binding.get("source_type")
        if source_type == "concept":
            expected = {"slot_id", "source_type", "concept_id", "selector"}
            if (
                set(binding) != expected
                or binding.get("concept_id") not in CONCEPTS
                or binding.get("selector") not in ALLOWED_SELECTORS
            ):
                raise ValueError(f"binding {index} concept fields are invalid")
            normalized.append(dict(binding))
        elif source_type == "constant":
            expected = {"slot_id", "source_type", "value_type", "value"}
            if (
                set(binding) != expected
                or binding.get("value_type") not in {"number", "boolean"}
                or not valid_value(
                    binding.get("value"), binding.get("value_type")
                )
            ):
                raise ValueError(f"binding {index} constant fields are invalid")
            normalized.append(dict(binding))
        else:
            raise ValueError(f"binding {index} source_type is invalid")
    normalized.sort(key=lambda item: item["slot_id"])
    provisional = {
        "contract_version": "financial-data-binding-profile.v1",
        "name": name,
        "bindings": normalized,
    }
    payload = {
        **provisional,
        "binding_profile_id": f"fmrbp_{digest(provisional)[:24]}",
    }
    issues = validate_binding_profile(payload)
    if issues:
        raise ValueError("binding profile is invalid: " + "; ".join(issues))
    return payload


def validate_binding_profile(payload: Any) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("binding profile must be an object",)
    if set(payload) != {
        "contract_version",
        "binding_profile_id",
        "name",
        "bindings",
    }:
        issues.append("binding profile fields are invalid")
    if payload.get("contract_version") != "financial-data-binding-profile.v1":
        issues.append("unsupported binding profile contract_version")
    profile_id = payload.get("binding_profile_id")
    if not isinstance(profile_id, str) or not BINDING_PROFILE_ID_RE.fullmatch(
        profile_id
    ):
        issues.append("binding_profile_id is invalid")
    if not isinstance(payload.get("name"), str) or not payload.get("name"):
        issues.append("binding profile name must be non-empty")
    bindings = payload.get("bindings")
    slot_ids: list[str] = []
    if not isinstance(bindings, list):
        issues.append("bindings must be an array")
    else:
        for index, binding in enumerate(bindings):
            if not isinstance(binding, dict):
                issues.append(f"bindings[{index}] must be an object")
                continue
            slot_id = binding.get("slot_id")
            if not isinstance(slot_id, str) or not slot_id:
                issues.append(f"bindings[{index}].slot_id must be non-empty")
            else:
                slot_ids.append(slot_id)
            source_type = binding.get("source_type")
            if source_type == "concept":
                if set(binding) != {
                    "slot_id",
                    "source_type",
                    "concept_id",
                    "selector",
                }:
                    issues.append(f"bindings[{index}] concept fields are invalid")
                if binding.get("concept_id") not in CONCEPTS:
                    issues.append(f"bindings[{index}].concept_id is unknown")
                if binding.get("selector") not in ALLOWED_SELECTORS:
                    issues.append(f"bindings[{index}].selector is invalid")
            elif source_type == "constant":
                if set(binding) != {
                    "slot_id",
                    "source_type",
                    "value_type",
                    "value",
                }:
                    issues.append(f"bindings[{index}] constant fields are invalid")
                if binding.get("value_type") not in {"number", "boolean"}:
                    issues.append(f"bindings[{index}].value_type is invalid")
                elif not valid_value(
                    binding.get("value"), binding.get("value_type")
                ):
                    issues.append(f"bindings[{index}].value is invalid")
            else:
                issues.append(f"bindings[{index}].source_type is invalid")
        if len(slot_ids) != len(set(slot_ids)):
            issues.append("binding slot IDs must be unique")
    if isinstance(profile_id, str) and BINDING_PROFILE_ID_RE.fullmatch(
        profile_id
    ):
        candidate = dict(payload)
        candidate.pop("binding_profile_id", None)
        if profile_id != f"fmrbp_{digest(candidate)[:24]}":
            issues.append("binding_profile_id does not match payload")
    return tuple(dict.fromkeys(issues))


def plan_financial_input_bindings(
    package: dict[str, Any],
    mapping_result: dict[str, Any],
    binding_profile: dict[str, Any],
    *,
    write_plan: dict[str, Any],
    execution_receipt: dict[str, Any],
) -> dict[str, Any]:
    package_issues = validate_financial_data_package(package)
    if package_issues:
        raise ValueError(
            "financial data package is invalid: " + "; ".join(package_issues)
        )
    mapping_issues = validate_mapping_result(
        mapping_result,
        package=package,
    )
    if mapping_issues:
        raise ValueError(
            "financial data mapping result is invalid: "
            + "; ".join(mapping_issues)
        )
    binding_issues = validate_binding_profile(binding_profile)
    if binding_issues:
        raise ValueError(
            "financial data binding profile is invalid: "
            + "; ".join(binding_issues)
        )
    plan_issues = validate_workbook_write_plan_payload(write_plan)
    if plan_issues:
        raise ValueError(
            "workbook write plan is invalid: " + "; ".join(plan_issues)
        )
    receipt_issues = validate_workbook_execution_receipt_payload(
        execution_receipt,
        write_plan=write_plan,
    )
    if receipt_issues:
        raise ValueError(
            "execution receipt is invalid: " + "; ".join(receipt_issues)
        )

    profile_by_slot = {
        item["slot_id"]: item for item in binding_profile["bindings"]
    }
    period_order = [period["period_id"] for period in package["periods"]]
    concept_values: dict[str, dict[str, Decimal]] = defaultdict(dict)
    for item in mapping_result["concept_series"]:
        concept_values[item["concept_id"]][item["period_id"]] = Decimal(
            item["amount"]
        )

    bound: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for record in _reserved_records(write_plan):
        slot_id = record.get("slot_id")
        profile_item = profile_by_slot.get(slot_id)
        cell_count = _coordinate_cell_count(record["coordinate"])
        if profile_item is None:
            unresolved.append(
                {
                    "record_id": record["record_id"],
                    "slot_id": slot_id,
                    "reason": "binding_profile_missing_slot",
                }
            )
            continue
        if profile_item["source_type"] == "constant":
            bound.append(
                {
                    "record_id": record["record_id"],
                    "slot_id": slot_id,
                    "value_type": profile_item["value_type"],
                    "values": [profile_item["value"]] * cell_count,
                    "source_ref": (
                        "financial-binding-profile:"
                        f"{binding_profile['binding_profile_id']}:{slot_id}"
                    ),
                }
            )
            continue

        concept_id = profile_item["concept_id"]
        available = concept_values.get(concept_id, {})
        ordered = [
            available[period_id]
            for period_id in period_order
            if period_id in available
        ]
        selector = profile_item["selector"]
        if not ordered:
            unresolved.append(
                {
                    "record_id": record["record_id"],
                    "slot_id": slot_id,
                    "reason": f"concept_has_no_values:{concept_id}",
                }
            )
            continue
        if selector == "period_series":
            selected = ordered
        elif selector == "latest":
            selected = [ordered[-1]]
        else:
            selected = [ordered[-1]] * cell_count
        if len(selected) != cell_count:
            unresolved.append(
                {
                    "record_id": record["record_id"],
                    "slot_id": slot_id,
                    "reason": (
                        "concept_value_count_mismatch:"
                        f"{concept_id}:{len(selected)}:{cell_count}"
                    ),
                }
            )
            continue
        bound.append(
            {
                "record_id": record["record_id"],
                "slot_id": slot_id,
                "value_type": "number",
                "values": [json_number(value) for value in selected],
                "source_ref": (
                    f"financial-data:{package['package_id']}:"
                    f"{concept_id}:{selector}"
                ),
            }
        )

    blockers = [
        f"{item['record_id']}:{item['reason']}" for item in unresolved
    ]
    if not mapping_result["ready_for_binding"]:
        blockers.extend(
            f"mapping:{item}" for item in mapping_result.get("blockers", [])
        )
    provisional = {
        "contract_version": "workbook-input-binding-plan.v1",
        "package_id": package["package_id"],
        "package_sha256": digest(package),
        "mapping_id": mapping_result["mapping_id"],
        "mapping_sha256": digest(mapping_result),
        "binding_profile_id": binding_profile["binding_profile_id"],
        "binding_profile_sha256": digest(binding_profile),
        "write_plan_id": write_plan["write_plan_id"],
        "write_plan_sha256": digest(write_plan),
        "execution_id": execution_receipt["execution_id"],
        "execution_receipt_sha256": digest(execution_receipt),
        "bound_records": bound,
        "unresolved_records": unresolved,
        "ready_for_input_set": not blockers,
        "blockers": list(dict.fromkeys(blockers)),
        "controls": list(BINDING_CONTROLS),
    }
    return {
        **provisional,
        "binding_plan_id": f"fmrbd_{digest(provisional)[:24]}",
    }


def validate_binding_plan(
    payload: Any,
    *,
    package: dict[str, Any] | None = None,
    mapping_result: dict[str, Any] | None = None,
    binding_profile: dict[str, Any] | None = None,
    write_plan: dict[str, Any] | None = None,
    execution_receipt: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("binding plan must be an object",)
    expected = {
        "contract_version",
        "binding_plan_id",
        "package_id",
        "package_sha256",
        "mapping_id",
        "mapping_sha256",
        "binding_profile_id",
        "binding_profile_sha256",
        "write_plan_id",
        "write_plan_sha256",
        "execution_id",
        "execution_receipt_sha256",
        "bound_records",
        "unresolved_records",
        "ready_for_input_set",
        "blockers",
        "controls",
    }
    if set(payload) != expected:
        issues.append("binding plan fields are invalid")
    if payload.get("contract_version") != "workbook-input-binding-plan.v1":
        issues.append("unsupported binding plan contract_version")
    plan_id = payload.get("binding_plan_id")
    if not isinstance(plan_id, str) or not BINDING_PLAN_ID_RE.fullmatch(plan_id):
        issues.append("binding_plan_id is invalid")
    blockers = payload.get("blockers")
    if not isinstance(blockers, list) or not all(
        isinstance(item, str) and item for item in blockers
    ):
        issues.append("blockers must be an array of strings")
    if payload.get("ready_for_input_set") is not (not bool(blockers)):
        issues.append("ready_for_input_set does not match blockers")
    if payload.get("controls") != list(BINDING_CONTROLS):
        issues.append("binding controls are invalid")
    if package is not None:
        if payload.get("package_id") != package.get("package_id"):
            issues.append("package_id does not match package")
        if payload.get("package_sha256") != digest(package):
            issues.append("package_sha256 does not match package")
    if mapping_result is not None:
        if payload.get("mapping_id") != mapping_result.get("mapping_id"):
            issues.append("mapping_id does not match mapping result")
        if payload.get("mapping_sha256") != digest(mapping_result):
            issues.append("mapping_sha256 does not match mapping result")
    if binding_profile is not None:
        if payload.get("binding_profile_id") != binding_profile.get(
            "binding_profile_id"
        ):
            issues.append("binding_profile_id does not match profile")
        if payload.get("binding_profile_sha256") != digest(binding_profile):
            issues.append("binding_profile_sha256 does not match profile")
    if write_plan is not None:
        if payload.get("write_plan_id") != write_plan.get("write_plan_id"):
            issues.append("write_plan_id does not match write plan")
        if payload.get("write_plan_sha256") != digest(write_plan):
            issues.append("write_plan_sha256 does not match write plan")
    if execution_receipt is not None:
        if payload.get("execution_id") != execution_receipt.get("execution_id"):
            issues.append("execution_id does not match execution receipt")
        if payload.get("execution_receipt_sha256") != digest(
            execution_receipt
        ):
            issues.append(
                "execution_receipt_sha256 does not match execution receipt"
            )
    if isinstance(plan_id, str) and BINDING_PLAN_ID_RE.fullmatch(plan_id):
        candidate = dict(payload)
        candidate.pop("binding_plan_id", None)
        if plan_id != f"fmrbd_{digest(candidate)[:24]}":
            issues.append("binding_plan_id does not match payload")
    return tuple(dict.fromkeys(issues))


def compile_input_set_from_binding_plan(
    binding_plan: dict[str, Any],
    *,
    write_plan: dict[str, Any],
    execution_receipt: dict[str, Any],
) -> dict[str, Any]:
    issues = validate_binding_plan(
        binding_plan,
        write_plan=write_plan,
        execution_receipt=execution_receipt,
    )
    if issues:
        raise ValueError("binding plan is invalid: " + "; ".join(issues))
    if not binding_plan["ready_for_input_set"]:
        raise ValueError("binding plan is not ready for an input set")

    rendered = json.dumps(
        binding_plan,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    provisional = {
        "contract_version": "workbook-input-set.v1",
        "write_plan_id": write_plan["write_plan_id"],
        "write_plan_sha256": digest(write_plan),
        "execution_id": execution_receipt["execution_id"],
        "execution_receipt_sha256": digest(execution_receipt),
        "source": {
            "kind": "system",
            "reference": (
                "financial-data-binding-plan:"
                f"{binding_plan['binding_plan_id']}"
            ),
            "sha256": hashlib.sha256(rendered).hexdigest(),
            "size_bytes": len(rendered),
        },
        "bindings": [
            {
                "record_id": item["record_id"],
                "value_type": item["value_type"],
                "values": item["values"],
                "source_ref": item["source_ref"],
            }
            for item in binding_plan["bound_records"]
        ],
        "controls": list(_INPUT_SET_CONTROLS),
    }
    payload = {
        **provisional,
        "input_set_id": f"fmri_{digest(provisional)[:24]}",
    }
    input_issues = validate_workbook_input_set_payload(
        payload,
        write_plan=write_plan,
        execution_receipt=execution_receipt,
    )
    if input_issues:
        raise ValueError(
            "compiled input set is invalid: " + "; ".join(input_issues)
        )
    return payload


def _reserved_records(write_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        record
        for phase in write_plan.get("phases", [])
        for record in phase.get("records", [])
        if isinstance(record, dict) and record.get("write_kind") == "reserve_input"
    ]


def _coordinate_cell_count(coordinate: str) -> int:
    match = _RANGE_RE.fullmatch(coordinate or "")
    if not match:
        raise ValueError("coordinate is invalid")
    start_col, start_row, end_col, end_row = match.groups()
    end_col = end_col or start_col
    end_row = end_row or start_row
    return (
        (_column_number(end_col) - _column_number(start_col) + 1)
        * (int(end_row) - int(start_row) + 1)
    )


def _column_number(label: str) -> int:
    value = 0
    for character in label:
        value = value * 26 + (ord(character) - ord("A") + 1)
    return value


__all__ = [
    "build_binding_profile",
    "compile_input_set_from_binding_plan",
    "plan_financial_input_bindings",
    "validate_binding_plan",
    "validate_binding_profile",
]
