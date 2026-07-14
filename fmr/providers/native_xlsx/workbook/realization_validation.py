from __future__ import annotations

from typing import Any

from fmr.providers.native_xlsx.workbook.realization_plan import (
    validate_workbook_realization_plan_payload as _base_validate,
)

_OPERATION_FIELDS = {
    "sequence",
    "operation_id",
    "source_operation",
    "content_plan_status",
    "status",
    "title",
    "slots",
    "blockers",
}
_SLOT_FIELDS = {
    "slot_id",
    "sheet_name",
    "sheet_position",
    "coordinate",
    "content_kind",
    "label",
    "identifier",
    "editable",
    "formula_binding",
    "style_binding",
    "reference_binding",
}
_FORMULA_FIELDS = {
    "resolved_identifier",
    "formula_spec_ref",
    "formula_kind",
    "expression_language",
    "expression_template",
    "dependencies",
    "output_type",
    "sign_convention",
    "fill_policy",
    "circularity_policy",
}
_DEPENDENCY_FIELDS = {
    "name",
    "binding_type",
    "identifier",
    "required",
    "target",
}
_TARGET_FIELDS = {
    "operation_id",
    "source_operation",
    "slot_id",
    "sheet_name",
    "sheet_position",
    "coordinate",
    "content_kind",
}
_STYLE_FIELDS = {
    "style_spec_ref",
    "number_format_spec_ref",
    "semantic_type",
    "role_style",
    "number_format",
}
_REFERENCE_FIELDS = {"binding_type", "identifier"}
_ALLOWED_KINDS = {
    "formula_identifier",
    "input_placeholder",
    "label",
    "period_header",
    "reference_identifier",
    "validation_identifier",
}
_ALLOWED_FORMULA_KINDS = {"calculation", "copy_rule", "validation"}
_ALLOWED_BINDING_TYPES = {
    "content_slot",
    "period_context",
    "reference_target",
    "source_workbook",
    "validation_context",
}


def validate_workbook_realization_plan_payload(
    payload: Any,
    *,
    content_plan: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    issues = list(_base_validate(payload, content_plan=content_plan))
    if not isinstance(payload, dict):
        return tuple(dict.fromkeys(issues))
    operations = payload.get("operation_realizations")
    if isinstance(operations, list):
        _validate_operations(operations, issues)
    return tuple(dict.fromkeys(issues))


def _validate_operations(operations: list[Any], issues: list[str]) -> None:
    for operation_index, operation in enumerate(operations):
        context = f"operation_realizations[{operation_index}]"
        if not isinstance(operation, dict):
            continue
        _reject_extra_keys(operation, _OPERATION_FIELDS, context, issues)
        if not isinstance(operation.get("sequence"), int) or isinstance(
            operation.get("sequence"), bool
        ):
            issues.append(f"{context}.sequence must be an integer")
        for field in ("operation_id", "source_operation", "content_plan_status", "status", "title"):
            if not isinstance(operation.get(field), str) or not operation.get(field):
                issues.append(f"{context}.{field} must be a non-empty string")
        slots = operation.get("slots")
        if isinstance(slots, list):
            seen_slots: set[str] = set()
            for slot_index, slot in enumerate(slots):
                slot_context = f"{context}.slots[{slot_index}]"
                _validate_slot(slot, slot_context, seen_slots, issues)


def _validate_slot(
    slot: Any,
    context: str,
    seen_slots: set[str],
    issues: list[str],
) -> None:
    if not isinstance(slot, dict):
        issues.append(f"{context} must be an object")
        return
    _reject_extra_keys(slot, _SLOT_FIELDS, context, issues)
    slot_id = slot.get("slot_id")
    if not isinstance(slot_id, str) or not slot_id:
        issues.append(f"{context}.slot_id must be a non-empty string")
    elif slot_id in seen_slots:
        issues.append(f"{context}.slot_id is duplicated")
    else:
        seen_slots.add(slot_id)
    if slot.get("content_kind") not in _ALLOWED_KINDS:
        issues.append(f"{context}.content_kind is invalid")
    if not isinstance(slot.get("editable"), bool):
        issues.append(f"{context}.editable must be boolean")
    for field in ("sheet_name", "coordinate", "label", "identifier"):
        if slot.get(field) is not None and not isinstance(slot.get(field), str):
            issues.append(f"{context}.{field} must be a string or null")
    if slot.get("sheet_position") is not None and (
        not isinstance(slot.get("sheet_position"), int)
        or isinstance(slot.get("sheet_position"), bool)
        or slot["sheet_position"] < 1
    ):
        issues.append(f"{context}.sheet_position must be a positive integer or null")

    formula = slot.get("formula_binding")
    if formula is not None:
        _validate_formula(formula, f"{context}.formula_binding", issues)
    style = slot.get("style_binding")
    if style is not None:
        _validate_style(style, f"{context}.style_binding", issues)
    reference = slot.get("reference_binding")
    if reference is not None:
        _validate_reference(reference, f"{context}.reference_binding", issues)


def _validate_formula(value: Any, context: str, issues: list[str]) -> None:
    if not isinstance(value, dict):
        issues.append(f"{context} must be an object or null")
        return
    _reject_extra_keys(value, _FORMULA_FIELDS, context, issues)
    for field in (
        "resolved_identifier",
        "formula_spec_ref",
        "expression_language",
        "expression_template",
        "output_type",
        "sign_convention",
        "fill_policy",
        "circularity_policy",
    ):
        if not isinstance(value.get(field), str) or not value.get(field):
            issues.append(f"{context}.{field} must be a non-empty string")
    if value.get("formula_kind") not in _ALLOWED_FORMULA_KINDS:
        issues.append(f"{context}.formula_kind is invalid")
    dependencies = value.get("dependencies")
    if not isinstance(dependencies, list):
        issues.append(f"{context}.dependencies must be an array")
    else:
        names: set[str] = set()
        for index, dependency in enumerate(dependencies):
            dependency_context = f"{context}.dependencies[{index}]"
            if not isinstance(dependency, dict):
                issues.append(f"{dependency_context} must be an object")
                continue
            _reject_extra_keys(dependency, _DEPENDENCY_FIELDS, dependency_context, issues)
            name = dependency.get("name")
            if not isinstance(name, str) or not name:
                issues.append(f"{dependency_context}.name must be a non-empty string")
            elif name in names:
                issues.append(f"{dependency_context}.name is duplicated")
            else:
                names.add(name)
            if dependency.get("binding_type") not in _ALLOWED_BINDING_TYPES:
                issues.append(f"{dependency_context}.binding_type is invalid")
            if not isinstance(dependency.get("identifier"), str) or not dependency.get("identifier"):
                issues.append(f"{dependency_context}.identifier must be a non-empty string")
            if not isinstance(dependency.get("required"), bool):
                issues.append(f"{dependency_context}.required must be boolean")
            target = dependency.get("target")
            if target is not None:
                if not isinstance(target, dict):
                    issues.append(f"{dependency_context}.target must be an object or null")
                else:
                    _reject_extra_keys(target, _TARGET_FIELDS, f"{dependency_context}.target", issues)


def _validate_style(value: Any, context: str, issues: list[str]) -> None:
    if not isinstance(value, dict):
        issues.append(f"{context} must be an object or null")
        return
    _reject_extra_keys(value, _STYLE_FIELDS, context, issues)
    for field in ("style_spec_ref", "number_format_spec_ref", "semantic_type"):
        if not isinstance(value.get(field), str) or not value.get(field):
            issues.append(f"{context}.{field} must be a non-empty string")
    for field in ("role_style", "number_format"):
        if not isinstance(value.get(field), dict):
            issues.append(f"{context}.{field} must be an object")


def _validate_reference(value: Any, context: str, issues: list[str]) -> None:
    if not isinstance(value, dict):
        issues.append(f"{context} must be an object or null")
        return
    _reject_extra_keys(value, _REFERENCE_FIELDS, context, issues)
    if value.get("binding_type") != "reference_target":
        issues.append(f"{context}.binding_type must be reference_target")
    if not isinstance(value.get("identifier"), str) or not value.get("identifier"):
        issues.append(f"{context}.identifier must be a non-empty string")


def _reject_extra_keys(
    payload: dict[str, Any],
    allowed: set[str],
    context: str,
    issues: list[str],
) -> None:
    extras = sorted(set(payload) - allowed)
    if extras:
        issues.append(f"{context} contains undeclared fields: {extras}")
