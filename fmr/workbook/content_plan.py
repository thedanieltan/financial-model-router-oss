from __future__ import annotations

import hashlib
import json
import re
import string
from typing import Any

from fmr.workbook.content_specs import CONTENT_SPECS, content_spec_registry_payload
from fmr.workbook.coordinate_plan import validate_workbook_coordinate_plan_payload

_PLAN_ID_RE = re.compile(r"^fmrt_[0-9a-f]{24}$")
_RANGE_RE = re.compile(r"^([A-Z]{1,3})([1-9][0-9]*):([A-Z]{1,3})([1-9][0-9]*)$")
_ALLOWED_STATUSES = {"blocked", "planned_content", "reference_only", "satisfied_existing"}
_ALLOWED_KINDS = {
    "input_placeholder",
    "label",
    "formula_identifier",
    "period_header",
    "reference_identifier",
    "validation_identifier",
}
_ALLOWED_FORMAT_ROLES = {
    "control",
    "header",
    "input",
    "label",
    "output",
    "period",
    "reference",
    "section_title",
    "subheader",
}
_ALLOWED_CONTROLS = {
    "content_planning_only",
    "content_specs_pinned",
    "coordinate_plan_pinned",
    "identifiers_only",
    "no_formula_expressions",
    "no_input_values",
    "no_workbook_mutation",
    "source_hash_pinned",
}
_FORBIDDEN_KEYS = {
    "cell_write",
    "color",
    "colour",
    "fill",
    "font",
    "formula",
    "macro",
    "number_format",
    "script",
    "value",
    "vba",
    "workbook_bytes",
}


def plan_workbook_content(coordinate_plan: dict[str, Any]) -> dict[str, Any]:
    coordinate_issues = validate_workbook_coordinate_plan_payload(coordinate_plan)
    if coordinate_issues:
        raise ValueError("invalid workbook coordinate plan: " + "; ".join(coordinate_issues))

    registry = content_spec_registry_payload()
    blockers: list[str] = []
    operation_contents: list[dict[str, Any]] = []

    if not coordinate_plan["ready_for_executor"]:
        blockers.extend(f"coordinate_plan:{item}" for item in coordinate_plan["blockers"])

    for operation in coordinate_plan["operation_plans"]:
        source_operation = operation["source_operation"]
        spec = CONTENT_SPECS[source_operation]
        operation_blockers: list[str] = []
        slots: list[dict[str, Any]] = []

        if operation["status"] == "blocked":
            status = "blocked"
            operation_blockers.extend(operation["blockers"] or ["coordinate_plan_blocked"])
        elif operation["status"] == "reference_only":
            status = "reference_only"
            slots = [_reference_slot(slot.to_dict()) for slot in spec.slots]
        elif operation["status"] == "satisfied_existing":
            status = "satisfied_existing"
        else:
            status = "planned_content"
            for allocation_index, allocation in enumerate(operation["allocations"], start=1):
                try:
                    if spec.template_kind == "period_extension":
                        slots.extend(
                            _period_extension_slots(
                                spec_payload=spec.to_dict(),
                                allocation=allocation,
                                allocation_index=allocation_index,
                            )
                        )
                    else:
                        slots.extend(
                            _allocation_slots(
                                spec_payload=spec.to_dict(),
                                allocation=allocation,
                                allocation_index=allocation_index,
                            )
                        )
                except ValueError as exc:
                    operation_blockers.append(str(exc))
            if operation_blockers:
                status = "blocked"

        operation_contents.append(
            {
                "sequence": operation["sequence"],
                "operation_id": operation["operation_id"],
                "source_operation": source_operation,
                "content_spec_ref": spec.specification_ref,
                "coordinate_plan_status": operation["status"],
                "status": status,
                "title": spec.title,
                "slots": slots,
                "validation_ids": list(spec.validation_ids),
                "blockers": list(dict.fromkeys(operation_blockers)),
            }
        )
        blockers.extend(
            f"{operation['operation_id']}:{item}"
            for item in dict.fromkeys(operation_blockers)
        )

    if not operation_contents:
        blockers.append("no_content_operations")

    deduplicated_blockers = tuple(dict.fromkeys(blockers))
    coordinate_plan_sha256 = _digest(coordinate_plan)
    controls = tuple(sorted(_ALLOWED_CONTROLS))
    provisional = {
        "contract_version": "workbook-content-plan.v1",
        "coordinate_plan_id": coordinate_plan["coordinate_plan_id"],
        "coordinate_plan_sha256": coordinate_plan_sha256,
        "content_specs_sha256": registry["registry_sha256"],
        "source": dict(coordinate_plan["source"]),
        "ready_for_executor": not deduplicated_blockers,
        "execution_supported_by_this_release": False,
        "blockers": list(deduplicated_blockers),
        "operation_contents": operation_contents,
        "controls": list(controls),
    }
    return {
        **provisional,
        "content_plan_id": f"fmrt_{_digest(provisional)[:24]}",
    }


def validate_workbook_content_plan_payload(
    payload: Any,
    *,
    coordinate_plan: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("content plan must be an object",)
    _reject_extra_keys(
        payload,
        {
            "contract_version",
            "content_plan_id",
            "coordinate_plan_id",
            "coordinate_plan_sha256",
            "content_specs_sha256",
            "source",
            "ready_for_executor",
            "execution_supported_by_this_release",
            "blockers",
            "operation_contents",
            "controls",
        },
        "content plan",
        issues,
    )
    if payload.get("contract_version") != "workbook-content-plan.v1":
        issues.append("unsupported contract_version")
    if _contains_forbidden_key(payload):
        issues.append("content plan contains executable workbook fields")

    content_plan_id = payload.get("content_plan_id")
    if not isinstance(content_plan_id, str) or not _PLAN_ID_RE.fullmatch(content_plan_id):
        issues.append("content_plan_id is invalid")
    for field in ("coordinate_plan_id", "coordinate_plan_sha256", "content_specs_sha256"):
        if not isinstance(payload.get(field), str) or not payload.get(field):
            issues.append(f"{field} must be a non-empty string")
    for field in ("coordinate_plan_sha256", "content_specs_sha256"):
        if isinstance(payload.get(field), str) and not _is_sha256(payload[field]):
            issues.append(f"{field} must be a SHA-256 hex string")

    source = payload.get("source")
    if not isinstance(source, dict):
        issues.append("source must be an object")
    else:
        _reject_extra_keys(source, {"filename", "sha256", "size_bytes"}, "source", issues)
        if not isinstance(source.get("filename"), str) or not source.get("filename"):
            issues.append("source.filename must be a non-empty string")
        if not _is_sha256(source.get("sha256")):
            issues.append("source.sha256 must be a SHA-256 hex string")
        if not isinstance(source.get("size_bytes"), int) or source.get("size_bytes") < 0:
            issues.append("source.size_bytes must be a non-negative integer")

    for field in ("ready_for_executor", "execution_supported_by_this_release"):
        if not isinstance(payload.get(field), bool):
            issues.append(f"{field} must be boolean")
    if payload.get("execution_supported_by_this_release") is not False:
        issues.append("execution_supported_by_this_release must be false for this release")

    blockers = payload.get("blockers")
    if not _is_string_list(blockers):
        issues.append("blockers must be an array of strings")
    elif payload.get("ready_for_executor") is not (len(blockers) == 0):
        issues.append("ready_for_executor does not match blockers")

    contents = payload.get("operation_contents")
    if not isinstance(contents, list):
        issues.append("operation_contents must be an array")
    else:
        _validate_operation_contents(contents, issues)

    controls = payload.get("controls")
    if not _is_string_list(controls):
        issues.append("controls must be an array of strings")
    elif set(controls) != _ALLOWED_CONTROLS or len(controls) != len(_ALLOWED_CONTROLS):
        issues.append("controls do not match the required control set")

    if isinstance(content_plan_id, str) and _PLAN_ID_RE.fullmatch(content_plan_id):
        candidate = dict(payload)
        candidate.pop("content_plan_id", None)
        expected_id = f"fmrt_{_digest(candidate)[:24]}"
        if content_plan_id != expected_id:
            issues.append("content_plan_id does not match payload")

    if coordinate_plan is not None:
        try:
            expected = plan_workbook_content(coordinate_plan)
        except ValueError as exc:
            issues.append(f"deterministic recomputation failed: {exc}")
        else:
            if payload != expected:
                issues.append("content plan does not match deterministic recomputation")

    return tuple(dict.fromkeys(issues))


def _allocation_slots(
    *,
    spec_payload: dict[str, Any],
    allocation: dict[str, Any],
    allocation_index: int,
) -> list[dict[str, Any]]:
    start_row = allocation["start"]["row"]
    start_column = allocation["start"]["column"]
    end_row = allocation["end"]["row"]
    end_column = allocation["end"]["column"]
    slots: list[dict[str, Any]] = []
    for slot in spec_payload["slots"]:
        relative = slot["relative_position"]
        slot_start_row = start_row + relative["row_offset"]
        slot_start_column = start_column + relative["column_offset"]
        slot_end_row = slot_start_row + relative["row_span"] - 1
        slot_end_column = slot_start_column + relative["column_span"] - 1
        if slot_end_row > end_row or slot_end_column > end_column:
            raise ValueError(
                f"content_slot_outside_allocation:{allocation['sheet_name']}:{slot['slot_id']}"
            )
        slots.append(
            _placed_slot(
                slot=slot,
                allocation=allocation,
                allocation_index=allocation_index,
                coordinate=_a1_range(
                    slot_start_row,
                    slot_start_column,
                    slot_end_row,
                    slot_end_column,
                ),
            )
        )
    return slots


def _period_extension_slots(
    *,
    spec_payload: dict[str, Any],
    allocation: dict[str, Any],
    allocation_index: int,
) -> list[dict[str, Any]]:
    start_row = allocation["start"]["row"]
    end_row = allocation["end"]["row"]
    start_column = allocation["start"]["column"]
    end_column = allocation["end"]["column"]
    slots: list[dict[str, Any]] = []
    for period_index, column in enumerate(range(start_column, end_column + 1), start=1):
        header_slot = spec_payload["slots"][0]
        body_slot = spec_payload["slots"][1]
        slots.append(
            _placed_slot(
                slot={
                    **header_slot,
                    "slot_id": f"period_{period_index}_header",
                    "identifier": f"fmr.period.forecast_{period_index}.v1",
                },
                allocation=allocation,
                allocation_index=allocation_index,
                coordinate=_a1_range(start_row, column, start_row, column),
            )
        )
        if end_row > start_row:
            slots.append(
                _placed_slot(
                    slot={
                        **body_slot,
                        "slot_id": f"period_{period_index}_body",
                        "identifier": f"fmr.formula.forecast_column_{period_index}.v1",
                    },
                    allocation=allocation,
                    allocation_index=allocation_index,
                    coordinate=_a1_range(start_row + 1, column, end_row, column),
                )
            )
    return slots


def _placed_slot(
    *,
    slot: dict[str, Any],
    allocation: dict[str, Any],
    allocation_index: int,
    coordinate: str,
) -> dict[str, Any]:
    return {
        "slot_id": f"a{allocation_index}_{slot['slot_id']}",
        "sheet_name": allocation["sheet_name"],
        "sheet_position": allocation["sheet_position"],
        "coordinate": coordinate,
        "content_kind": slot["content_kind"],
        "label": slot["label"],
        "identifier": slot["identifier"],
        "format_role": slot["format_role"],
        "editable": slot["editable"],
    }


def _reference_slot(slot: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot_id": slot["slot_id"],
        "sheet_name": None,
        "sheet_position": None,
        "coordinate": None,
        "content_kind": slot["content_kind"],
        "label": slot["label"],
        "identifier": slot["identifier"],
        "format_role": slot["format_role"],
        "editable": slot["editable"],
    }


def _validate_operation_contents(contents: list[Any], issues: list[str]) -> None:
    seen_operation_ids: set[str] = set()
    for index, item in enumerate(contents):
        context = f"operation_contents[{index}]"
        if not isinstance(item, dict):
            issues.append(f"{context} must be an object")
            continue
        _reject_extra_keys(
            item,
            {
                "sequence",
                "operation_id",
                "source_operation",
                "content_spec_ref",
                "coordinate_plan_status",
                "status",
                "title",
                "slots",
                "validation_ids",
                "blockers",
            },
            context,
            issues,
        )
        if not isinstance(item.get("sequence"), int) or item.get("sequence") < 1:
            issues.append(f"{context}.sequence must be a positive integer")
        operation_id = item.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            issues.append(f"{context}.operation_id must be a non-empty string")
        elif operation_id in seen_operation_ids:
            issues.append(f"duplicate operation_id: {operation_id}")
        else:
            seen_operation_ids.add(operation_id)
        source_operation = item.get("source_operation")
        if source_operation not in CONTENT_SPECS:
            issues.append(f"{context}.source_operation is unsupported")
        if item.get("status") not in _ALLOWED_STATUSES:
            issues.append(f"{context}.status is invalid")
        for field in ("content_spec_ref", "coordinate_plan_status", "title"):
            if not isinstance(item.get(field), str) or not item.get(field):
                issues.append(f"{context}.{field} must be a non-empty string")
        if not _is_string_list(item.get("validation_ids")):
            issues.append(f"{context}.validation_ids must be an array of strings")
        if not _is_string_list(item.get("blockers")):
            issues.append(f"{context}.blockers must be an array of strings")
        slots = item.get("slots")
        if not isinstance(slots, list):
            issues.append(f"{context}.slots must be an array")
        else:
            _validate_slots(slots, context, issues)


def _validate_slots(slots: list[Any], context: str, issues: list[str]) -> None:
    seen: set[str] = set()
    for index, slot in enumerate(slots):
        slot_context = f"{context}.slots[{index}]"
        if not isinstance(slot, dict):
            issues.append(f"{slot_context} must be an object")
            continue
        _reject_extra_keys(
            slot,
            {
                "slot_id",
                "sheet_name",
                "sheet_position",
                "coordinate",
                "content_kind",
                "label",
                "identifier",
                "format_role",
                "editable",
            },
            slot_context,
            issues,
        )
        slot_id = slot.get("slot_id")
        if not isinstance(slot_id, str) or not slot_id:
            issues.append(f"{slot_context}.slot_id must be a non-empty string")
        elif slot_id in seen:
            issues.append(f"{context} has duplicate slot_id: {slot_id}")
        else:
            seen.add(slot_id)
        if slot.get("content_kind") not in _ALLOWED_KINDS:
            issues.append(f"{slot_context}.content_kind is invalid")
        if slot.get("format_role") not in _ALLOWED_FORMAT_ROLES:
            issues.append(f"{slot_context}.format_role is invalid")
        if not isinstance(slot.get("editable"), bool):
            issues.append(f"{slot_context}.editable must be boolean")
        coordinate = slot.get("coordinate")
        if coordinate is not None and (
            not isinstance(coordinate, str) or not _RANGE_RE.fullmatch(coordinate)
        ):
            issues.append(f"{slot_context}.coordinate must be an A1 range or null")
        sheet_name = slot.get("sheet_name")
        sheet_position = slot.get("sheet_position")
        if coordinate is None:
            if sheet_name is not None or sheet_position is not None:
                issues.append(f"{slot_context} reference slots must not carry sheet coordinates")
        else:
            if not isinstance(sheet_name, str) or not sheet_name:
                issues.append(f"{slot_context}.sheet_name must be a non-empty string")
            if not isinstance(sheet_position, int) or sheet_position < 1:
                issues.append(f"{slot_context}.sheet_position must be a positive integer")


def _a1_range(start_row: int, start_column: int, end_row: int, end_column: int) -> str:
    return f"{_column_name(start_column)}{start_row}:{_column_name(end_column)}{end_row}"


def _column_name(column: int) -> str:
    name = ""
    value = column
    while value:
        value, remainder = divmod(value - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _reject_extra_keys(
    payload: dict[str, Any],
    allowed: set[str],
    context: str,
    issues: list[str],
) -> None:
    extras = sorted(set(payload) - allowed)
    if extras:
        issues.append(f"{context} contains unsupported fields: {', '.join(extras)}")


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in _FORBIDDEN_KEYS:
                return True
            if _contains_forbidden_key(item):
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


def _digest(payload: Any) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()
