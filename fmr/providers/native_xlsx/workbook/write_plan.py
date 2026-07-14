from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from fmr.providers.native_xlsx.workbook.realization_plan import validate_workbook_realization_plan_payload

_WRITE_PLAN_ID_RE = re.compile(r"^fmrw_[0-9a-f]{24}$")
_RANGE_RE = re.compile(r"^([A-Z]{1,3})([1-9][0-9]*)(?::([A-Z]{1,3})([1-9][0-9]*))?$")
_IDENTIFIER_RE = re.compile(r"^fmr\.[a-z0-9_.-]+\.v1$")
_TOKEN_RE = re.compile(r"\s*(\{\{[a-z][a-z0-9_]*\}\}|[A-Z][A-Z0-9_]*|[0-9]+(?:\.[0-9]+)?|[,()])")
_FORECAST_PERIOD_RE = re.compile(r"^fmr\.period\.forecast_([1-9][0-9]*)\.v1$")

_ALLOWED_CONTROLS = {
    "absolute_references_only",
    "context_bindings_explicit",
    "dry_run_only",
    "formula_language_compiled",
    "no_external_links",
    "no_macro_or_vba",
    "no_workbook_mutation",
    "ordered_write_phases",
    "realization_plan_pinned",
    "source_hash_pinned",
}
_ALLOWED_WRITE_KINDS = {
    "apply_style",
    "ensure_sheet",
    "reserve_input",
    "write_formula",
    "write_value",
}
_ALLOWED_BINDING_TYPES = {"constant", "range"}
_FORBIDDEN_KEYS = {"workbook_bytes", "macro", "vba", "script", "execute"}


@dataclass(frozen=True)
class Rectangle:
    start_row: int
    start_column: int
    end_row: int
    end_column: int

    @property
    def rows(self) -> int:
        return self.end_row - self.start_row + 1

    @property
    def columns(self) -> int:
        return self.end_column - self.start_column + 1

    def cells(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (row, column)
            for row in range(self.start_row, self.end_row + 1)
            for column in range(self.start_column, self.end_column + 1)
        )


@dataclass(frozen=True)
class Operand:
    current: str
    previous: str | None = None


def compile_workbook_write_plan(
    realization_plan: dict[str, Any],
    write_context: dict[str, Any],
) -> dict[str, Any]:
    realization_issues = validate_workbook_realization_plan_payload(realization_plan)
    if realization_issues:
        raise ValueError("invalid workbook realization plan: " + "; ".join(realization_issues))
    context_issues = validate_workbook_write_context_payload(write_context)
    if context_issues:
        raise ValueError("invalid workbook write context: " + "; ".join(context_issues))

    blockers: list[str] = []
    records_by_phase: dict[int, list[dict[str, Any]]] = {10: [], 20: [], 30: [], 40: []}
    sequence = 0

    if not realization_plan["ready_for_executor"]:
        blockers.extend(f"realization_plan:{item}" for item in realization_plan["blockers"])

    sheets: dict[str, int] = {}
    for operation in realization_plan["operation_realizations"]:
        for slot in operation["slots"]:
            sheet_name = slot.get("sheet_name")
            sheet_position = slot.get("sheet_position")
            if isinstance(sheet_name, str) and isinstance(sheet_position, int):
                sheets[sheet_name] = min(sheet_position, sheets.get(sheet_name, sheet_position))

    for sheet_name, sheet_position in sorted(sheets.items(), key=lambda item: (item[1], item[0])):
        sequence += 1
        records_by_phase[10].append(
            _record(
                sequence,
                "ensure_sheet",
                sheet_name=sheet_name,
                sheet_position=sheet_position,
                coordinate=None,
                payload={"mode": "ensure", "position": sheet_position},
            )
        )

    for operation in sorted(realization_plan["operation_realizations"], key=lambda item: item["sequence"]):
        if operation["status"] == "blocked":
            blockers.extend(
                f"{operation['operation_id']}:{item}"
                for item in operation["blockers"] or ["realization_blocked"]
            )
            continue
        if operation["status"] in {"reference_only", "satisfied_existing"}:
            continue

        for slot in operation["slots"]:
            coordinate = slot.get("coordinate")
            sheet_name = slot.get("sheet_name")
            sheet_position = slot.get("sheet_position")
            if not isinstance(coordinate, str) or not isinstance(sheet_name, str):
                continue
            try:
                rectangle = _parse_range(coordinate)
            except ValueError as exc:
                blockers.append(f"{operation['operation_id']}:{slot['slot_id']}:{exc}")
                continue

            content_kind = slot["content_kind"]
            if content_kind == "label":
                sequence += 1
                records_by_phase[20].append(
                    _record(
                        sequence,
                        "write_value",
                        sheet_name=sheet_name,
                        sheet_position=sheet_position,
                        coordinate=_cell_range(rectangle.start_row, rectangle.start_column),
                        payload={"value_type": "string", "value": slot["label"]},
                        operation_id=operation["operation_id"],
                        slot_id=slot["slot_id"],
                    )
                )
            elif content_kind == "period_header":
                labels, issue = _period_values(slot, rectangle, write_context["period_labels"])
                if issue:
                    blockers.append(f"{operation['operation_id']}:{slot['slot_id']}:{issue}")
                else:
                    for (row, column), label in zip(rectangle.cells(), labels, strict=True):
                        sequence += 1
                        records_by_phase[20].append(
                            _record(
                                sequence,
                                "write_value",
                                sheet_name=sheet_name,
                                sheet_position=sheet_position,
                                coordinate=_cell_range(row, column),
                                payload={"value_type": "string", "value": label},
                                operation_id=operation["operation_id"],
                                slot_id=slot["slot_id"],
                            )
                        )
            elif content_kind == "input_placeholder":
                sequence += 1
                records_by_phase[20].append(
                    _record(
                        sequence,
                        "reserve_input",
                        sheet_name=sheet_name,
                        sheet_position=sheet_position,
                        coordinate=coordinate,
                        payload={"value_type": "blank", "editable": True},
                        operation_id=operation["operation_id"],
                        slot_id=slot["slot_id"],
                    )
                )
            elif content_kind in {"formula_identifier", "validation_identifier"}:
                formulas, formula_issues = _compile_formula_slot(
                    slot,
                    output_rectangle=rectangle,
                    bindings=write_context["bindings"],
                )
                blockers.extend(
                    f"{operation['operation_id']}:{slot['slot_id']}:{item}"
                    for item in formula_issues
                )
                for coordinate_value, formula in formulas:
                    sequence += 1
                    binding = slot["formula_binding"]
                    records_by_phase[30].append(
                        _record(
                            sequence,
                            "write_formula",
                            sheet_name=sheet_name,
                            sheet_position=sheet_position,
                            coordinate=coordinate_value,
                            payload={
                                "formula": formula,
                                "formula_identifier": slot["identifier"],
                                "output_type": binding["output_type"],
                                "sign_convention": binding["sign_convention"],
                            },
                            operation_id=operation["operation_id"],
                            slot_id=slot["slot_id"],
                        )
                    )

            if slot.get("style_binding") is not None:
                sequence += 1
                records_by_phase[40].append(
                    _record(
                        sequence,
                        "apply_style",
                        sheet_name=sheet_name,
                        sheet_position=sheet_position,
                        coordinate=coordinate,
                        payload={"style": slot["style_binding"]},
                        operation_id=operation["operation_id"],
                        slot_id=slot["slot_id"],
                    )
                )

    phases = [
        {"phase": phase, "name": name, "records": records_by_phase[phase]}
        for phase, name in (
            (10, "sheet_setup"),
            (20, "values_and_inputs"),
            (30, "formulas_and_validations"),
            (40, "styles_and_protection"),
        )
    ]
    deduplicated_blockers = tuple(dict.fromkeys(blockers))
    provisional = {
        "contract_version": "workbook-write-plan.v1",
        "realization_plan_id": realization_plan["realization_plan_id"],
        "realization_plan_sha256": _digest(realization_plan),
        "write_context_sha256": _digest(write_context),
        "formula_language": "excel-a1.v1",
        "source": dict(realization_plan["source"]),
        "ready_for_executor": not deduplicated_blockers,
        "execution_supported_by_this_release": False,
        "blockers": list(deduplicated_blockers),
        "phases": phases,
        "write_record_count": sum(len(item["records"]) for item in phases),
        "controls": sorted(_ALLOWED_CONTROLS),
    }
    return {**provisional, "write_plan_id": f"fmrw_{_digest(provisional)[:24]}"}


def validate_workbook_write_context_payload(payload: Any) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("write context must be an object",)
    _reject_extra_keys(payload, {"contract_version", "period_labels", "bindings"}, "write context", issues)
    if payload.get("contract_version") != "workbook-write-context.v1":
        issues.append("unsupported write context contract_version")
    labels = payload.get("period_labels")
    if not isinstance(labels, list) or not labels or not all(isinstance(item, str) and item for item in labels):
        issues.append("period_labels must be a non-empty array of non-empty strings")
    bindings = payload.get("bindings")
    if not isinstance(bindings, dict):
        issues.append("bindings must be an object")
    else:
        for identifier, binding in bindings.items():
            context = f"bindings[{identifier!r}]"
            if not isinstance(identifier, str) or not _IDENTIFIER_RE.fullmatch(identifier):
                issues.append(f"{context} identifier is invalid")
            if not isinstance(binding, dict):
                issues.append(f"{context} must be an object")
                continue
            _reject_extra_keys(
                binding,
                {"binding_type", "sheet_name", "coordinate", "value", "alignment"},
                context,
                issues,
            )
            binding_type = binding.get("binding_type")
            if binding_type not in _ALLOWED_BINDING_TYPES:
                issues.append(f"{context}.binding_type is invalid")
            if binding_type == "range":
                if not isinstance(binding.get("sheet_name"), str) or not binding.get("sheet_name"):
                    issues.append(f"{context}.sheet_name must be non-empty")
                try:
                    _parse_range(binding.get("coordinate"))
                except ValueError:
                    issues.append(f"{context}.coordinate is invalid")
                if binding.get("alignment", "match") not in {"match", "whole_range"}:
                    issues.append(f"{context}.alignment is invalid")
                if "value" in binding:
                    issues.append(f"{context}.value is not allowed for a range binding")
            elif binding_type == "constant":
                value = binding.get("value")
                if isinstance(value, bool):
                    pass
                elif not isinstance(value, (int, float)):
                    issues.append(f"{context}.value must be numeric or boolean")
                if any(key in binding for key in ("sheet_name", "coordinate", "alignment")):
                    issues.append(f"{context} contains range fields for a constant binding")
    return tuple(dict.fromkeys(issues))


def validate_workbook_write_plan_payload(
    payload: Any,
    *,
    realization_plan: dict[str, Any] | None = None,
    write_context: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("write plan must be an object",)
    _reject_extra_keys(
        payload,
        {
            "contract_version",
            "write_plan_id",
            "realization_plan_id",
            "realization_plan_sha256",
            "write_context_sha256",
            "formula_language",
            "source",
            "ready_for_executor",
            "execution_supported_by_this_release",
            "blockers",
            "phases",
            "write_record_count",
            "controls",
        },
        "write plan",
        issues,
    )
    if payload.get("contract_version") != "workbook-write-plan.v1":
        issues.append("unsupported contract_version")
    if payload.get("formula_language") != "excel-a1.v1":
        issues.append("unsupported formula_language")
    if _contains_forbidden_key(payload):
        issues.append("write plan contains forbidden execution fields")
    plan_id = payload.get("write_plan_id")
    if not isinstance(plan_id, str) or not _WRITE_PLAN_ID_RE.fullmatch(plan_id):
        issues.append("write_plan_id is invalid")
    for field in ("realization_plan_id", "realization_plan_sha256", "write_context_sha256"):
        if not isinstance(payload.get(field), str) or not payload.get(field):
            issues.append(f"{field} must be a non-empty string")
    for field in ("realization_plan_sha256", "write_context_sha256"):
        if isinstance(payload.get(field), str) and not _is_sha256(payload[field]):
            issues.append(f"{field} must be a SHA-256 hex string")
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
    phases = payload.get("phases")
    record_count = 0
    if not isinstance(phases, list) or [item.get("phase") for item in phases if isinstance(item, dict)] != [10, 20, 30, 40]:
        issues.append("phases must contain the ordered phases 10, 20, 30 and 40")
    else:
        expected_sequence = 1
        for phase_index, phase in enumerate(phases):
            context = f"phases[{phase_index}]"
            _reject_extra_keys(phase, {"phase", "name", "records"}, context, issues)
            records = phase.get("records")
            if not isinstance(records, list):
                issues.append(f"{context}.records must be an array")
                continue
            record_count += len(records)
            for record_index, record in enumerate(records):
                record_context = f"{context}.records[{record_index}]"
                if not isinstance(record, dict):
                    issues.append(f"{record_context} must be an object")
                    continue
                _reject_extra_keys(
                    record,
                    {
                        "record_id",
                        "sequence",
                        "write_kind",
                        "operation_id",
                        "slot_id",
                        "sheet_name",
                        "sheet_position",
                        "coordinate",
                        "payload",
                    },
                    record_context,
                    issues,
                )
                if record.get("sequence") != expected_sequence:
                    issues.append(f"{record_context}.sequence is not contiguous")
                expected_sequence += 1
                if record.get("write_kind") not in _ALLOWED_WRITE_KINDS:
                    issues.append(f"{record_context}.write_kind is invalid")
                if record.get("record_id") != f"fmrw_{record.get('sequence', 0):06d}":
                    issues.append(f"{record_context}.record_id is invalid")
                coordinate = record.get("coordinate")
                if coordinate is not None:
                    try:
                        _parse_range(coordinate)
                    except ValueError:
                        issues.append(f"{record_context}.coordinate is invalid")
                if not isinstance(record.get("payload"), dict):
                    issues.append(f"{record_context}.payload must be an object")
                if record.get("write_kind") == "write_formula":
                    formula = record.get("payload", {}).get("formula")
                    if not isinstance(formula, str) or not formula.startswith("="):
                        issues.append(f"{record_context} formula must be an Excel formula")
                    elif "{{" in formula or "}}" in formula:
                        issues.append(f"{record_context} formula contains unresolved tokens")
    if payload.get("write_record_count") != record_count:
        issues.append("write_record_count does not match phases")
    controls = payload.get("controls")
    if not _is_string_list(controls) or set(controls) != _ALLOWED_CONTROLS:
        issues.append("controls do not match the required control set")
    if isinstance(plan_id, str) and _WRITE_PLAN_ID_RE.fullmatch(plan_id):
        candidate = dict(payload)
        candidate.pop("write_plan_id", None)
        if plan_id != f"fmrw_{_digest(candidate)[:24]}":
            issues.append("write_plan_id does not match payload")
    if realization_plan is not None and write_context is not None:
        try:
            expected = compile_workbook_write_plan(realization_plan, write_context)
        except ValueError as exc:
            issues.append(f"deterministic recomputation failed: {exc}")
        else:
            if payload != expected:
                issues.append("write plan does not match deterministic recomputation")
    return tuple(dict.fromkeys(issues))


def _record(
    sequence: int,
    write_kind: str,
    *,
    sheet_name: str,
    sheet_position: int | None,
    coordinate: str | None,
    payload: dict[str, Any],
    operation_id: str | None = None,
    slot_id: str | None = None,
) -> dict[str, Any]:
    return {
        "record_id": f"fmrw_{sequence:06d}",
        "sequence": sequence,
        "write_kind": write_kind,
        "operation_id": operation_id,
        "slot_id": slot_id,
        "sheet_name": sheet_name,
        "sheet_position": sheet_position,
        "coordinate": coordinate,
        "payload": payload,
    }


def _period_values(
    slot: dict[str, Any],
    rectangle: Rectangle,
    period_labels: list[str],
) -> tuple[tuple[str, ...], str | None]:
    identifier = slot.get("identifier")
    count = len(rectangle.cells())
    match = _FORECAST_PERIOD_RE.fullmatch(identifier or "")
    if match:
        index = int(match.group(1)) - 1
        if index >= len(period_labels):
            return (), f"period_label_missing:{identifier}"
        return (period_labels[index],), None
    if identifier == "fmr.period.series.v1":
        if len(period_labels) < count:
            return (), f"period_labels_insufficient:required={count}:available={len(period_labels)}"
        return tuple(period_labels[:count]), None
    return (), f"period_identifier_unsupported:{identifier}"


def _compile_formula_slot(
    slot: dict[str, Any],
    *,
    output_rectangle: Rectangle,
    bindings: dict[str, Any],
) -> tuple[list[tuple[str, str]], tuple[str, ...]]:
    formula_binding = slot.get("formula_binding")
    if not isinstance(formula_binding, dict):
        return [], ("formula_binding_missing",)
    cells = output_rectangle.cells()
    if formula_binding.get("fill_policy") == "single_cell":
        cells = cells[:1]
    formulas: list[tuple[str, str]] = []
    issues: list[str] = []
    for cell_index, (row, column) in enumerate(cells):
        operands: dict[str, Operand] = {}
        for dependency in formula_binding["dependencies"]:
            operand, issue = _resolve_operand(
                dependency,
                output_rectangle=output_rectangle,
                output_cell=(row, column),
                cell_index=cell_index,
                bindings=bindings,
            )
            if issue:
                issues.append(issue)
            elif operand is not None:
                operands[dependency["name"]] = operand
        if any(item.startswith("binding_") or item.startswith("dependency_") for item in issues):
            continue
        try:
            expression = _compile_expression(formula_binding["expression_template"], operands)
        except ValueError as exc:
            issues.append(str(exc))
            continue
        formulas.append((_cell_range(row, column), "=" + expression))
    return formulas, tuple(dict.fromkeys(issues))


def _resolve_operand(
    dependency: dict[str, Any],
    *,
    output_rectangle: Rectangle,
    output_cell: tuple[int, int],
    cell_index: int,
    bindings: dict[str, Any],
) -> tuple[Operand | None, str | None]:
    binding_type = dependency["binding_type"]
    identifier = dependency["identifier"]
    if binding_type == "content_slot":
        target = dependency.get("target")
        if not isinstance(target, dict):
            return None, f"dependency_unresolved:{identifier}"
        return _operand_from_range(
            target["sheet_name"],
            target["coordinate"],
            output_rectangle,
            output_cell,
            alignment="match",
        )
    if binding_type == "period_context":
        row, column = output_cell
        if identifier == "fmr.period-context.previous_period_formula.v1":
            if column <= 1:
                return None, f"dependency_previous_period_unavailable:{identifier}"
            return Operand(_qualified_cell(dependency.get("target", {}).get("sheet_name") or "", row, column - 1, qualify=False)), None
        if identifier == "fmr.period-context.period_index.v1":
            return Operand(str(cell_index + 1)), None
        return None, f"dependency_period_context_unsupported:{identifier}"
    binding = bindings.get(identifier)
    if binding is None:
        if dependency.get("required") is False:
            return Operand("0"), None
        return None, f"binding_missing:{identifier}"
    if binding["binding_type"] == "constant":
        value = binding["value"]
        if isinstance(value, bool):
            return Operand("TRUE" if value else "FALSE"), None
        return Operand(_number(value)), None
    alignment = binding.get("alignment", "match")
    if binding_type in {"validation_context", "reference_target"}:
        alignment = "whole_range"
    if identifier.endswith(".covenant_inputs.v1"):
        alignment = "whole_range"
    return _operand_from_range(
        binding["sheet_name"],
        binding["coordinate"],
        output_rectangle,
        output_cell,
        alignment=alignment,
    )


def _operand_from_range(
    sheet_name: str,
    coordinate: str,
    output_rectangle: Rectangle,
    output_cell: tuple[int, int],
    *,
    alignment: str,
) -> tuple[Operand | None, str | None]:
    try:
        target = _parse_range(coordinate)
    except ValueError:
        return None, f"binding_coordinate_invalid:{coordinate}"
    if alignment == "whole_range":
        return Operand(_qualified_range(sheet_name, target)), None
    row, column = output_cell
    row_offset = row - output_rectangle.start_row
    column_offset = column - output_rectangle.start_column
    if target.rows == 1 and target.columns == 1:
        target_row = target.start_row
        target_column = target.start_column
    elif target.rows == output_rectangle.rows and target.columns == output_rectangle.columns:
        target_row = target.start_row + row_offset
        target_column = target.start_column + column_offset
    elif target.rows == 1 and output_rectangle.rows == 1 and target.columns == output_rectangle.columns:
        target_row = target.start_row
        target_column = target.start_column + column_offset
    elif target.columns == 1 and output_rectangle.columns == 1 and target.rows == output_rectangle.rows:
        target_row = target.start_row + row_offset
        target_column = target.start_column
    elif target.columns == output_rectangle.columns:
        target_row = target.start_row
        target_column = target.start_column + column_offset
    elif target.rows == output_rectangle.rows:
        target_row = target.start_row + row_offset
        target_column = target.start_column
    else:
        return None, f"binding_shape_mismatch:{coordinate}"
    previous = None
    if target_column > target.start_column:
        previous = _qualified_cell(sheet_name, target_row, target_column - 1)
    return Operand(_qualified_cell(sheet_name, target_row, target_column), previous), None


def _compile_expression(template: str, operands: dict[str, Operand]) -> str:
    tokens = _tokenize(template)
    position = 0

    def parse() -> Any:
        nonlocal position
        if position >= len(tokens):
            raise ValueError("formula_expression_unexpected_end")
        token = tokens[position]
        position += 1
        if token.startswith("{{"):
            name = token[2:-2]
            if name not in operands:
                raise ValueError(f"formula_operand_missing:{name}")
            return ("operand", name)
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", token):
            return ("number", token)
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", token):
            if position >= len(tokens) or tokens[position] != "(":
                raise ValueError(f"formula_function_parenthesis_missing:{token}")
            position += 1
            arguments: list[Any] = []
            if position < len(tokens) and tokens[position] != ")":
                while True:
                    arguments.append(parse())
                    if position < len(tokens) and tokens[position] == ",":
                        position += 1
                        continue
                    break
            if position >= len(tokens) or tokens[position] != ")":
                raise ValueError(f"formula_function_unclosed:{token}")
            position += 1
            return ("function", token, arguments)
        raise ValueError(f"formula_token_unsupported:{token}")

    tree = parse()
    if position != len(tokens):
        raise ValueError("formula_expression_trailing_tokens")
    return _render_expression(tree, operands)


def _render_expression(node: Any, operands: dict[str, Operand]) -> str:
    kind = node[0]
    if kind == "number":
        return node[1]
    if kind == "operand":
        return operands[node[1]].current
    function = node[1]
    arguments = node[2]
    rendered = [_render_expression(item, operands) for item in arguments]
    if function == "ADD":
        return f"SUM({','.join(rendered)})"
    if function == "AVERAGE":
        return f"AVERAGE({','.join(rendered)})"
    if function == "CHANGE":
        if len(arguments) != 1 or arguments[0][0] != "operand":
            raise ValueError("formula_change_requires_dependency")
        operand = operands[arguments[0][1]]
        return "0" if operand.previous is None else f"({operand.current}-{operand.previous})"
    if function == "COPY_PREVIOUS_PERIOD":
        return rendered[0]
    if function == "COVENANT_METRIC":
        return f"SUM({rendered[0]})"
    if function == "DIVIDE":
        return f"({rendered[0]}/{rendered[1]})"
    if function == "DRIVER_FORECAST":
        return rendered[0]
    if function == "MAX":
        return f"MAX({','.join(rendered)})"
    if function == "MUL":
        return f"PRODUCT({','.join(rendered)})"
    if function == "NEGATE":
        return f"(-{rendered[0]})"
    if function == "POWER":
        return f"POWER({rendered[0]},{rendered[1]})"
    if function == "REFINANCING_SOURCES_USES":
        return rendered[0]
    if function == "RUN_VALIDATION":
        return f"AND({rendered[0]})"
    if function == "SENSITIVITY_GRID":
        return rendered[2]
    if function == "STRAIGHT_LINE_ROLLFORWARD":
        return f"(SUM({rendered[0]},{rendered[2]})/{rendered[1]})"
    if function == "SUB":
        return f"({rendered[0]}-{rendered[1]})"
    if function == "SUM":
        return f"SUM({','.join(rendered)})"
    if function == "WORKING_CAPITAL_FROM_DAYS":
        return (
            f"(({rendered[0]}*{rendered[2]}/365)+"
            f"({rendered[1]}*{rendered[3]}/365)-"
            f"({rendered[1]}*{rendered[4]}/365))"
        )
    raise ValueError(f"formula_function_unsupported:{function}")


def _tokenize(expression: str) -> tuple[str, ...]:
    tokens: list[str] = []
    position = 0
    while position < len(expression):
        match = _TOKEN_RE.match(expression, position)
        if match is None:
            raise ValueError(f"formula_expression_invalid_at:{position}")
        tokens.append(match.group(1))
        position = match.end()
    return tuple(tokens)


def _parse_range(value: Any) -> Rectangle:
    if not isinstance(value, str):
        raise ValueError("range must be a string")
    match = _RANGE_RE.fullmatch(value)
    if match is None:
        raise ValueError("range must be A1 or A1:B2")
    start_column = _column_number(match.group(1))
    start_row = int(match.group(2))
    end_column = _column_number(match.group(3) or match.group(1))
    end_row = int(match.group(4) or match.group(2))
    if end_row < start_row or end_column < start_column:
        raise ValueError("range end precedes start")
    return Rectangle(start_row, start_column, end_row, end_column)


def _qualified_range(sheet_name: str, rectangle: Rectangle) -> str:
    return (
        f"{_quote_sheet(sheet_name)}!"
        f"${_column_name(rectangle.start_column)}${rectangle.start_row}:"
        f"${_column_name(rectangle.end_column)}${rectangle.end_row}"
    )


def _qualified_cell(
    sheet_name: str,
    row: int,
    column: int,
    *,
    qualify: bool = True,
) -> str:
    cell = f"${_column_name(column)}${row}"
    return f"{_quote_sheet(sheet_name)}!{cell}" if qualify and sheet_name else cell


def _quote_sheet(sheet_name: str) -> str:
    return "'" + sheet_name.replace("'", "''") + "'"


def _cell_range(row: int, column: int) -> str:
    cell = f"{_column_name(column)}{row}"
    return f"{cell}:{cell}"


def _column_number(name: str) -> int:
    value = 0
    for character in name:
        value = value * 26 + ord(character) - 64
    return value


def _column_name(number: int) -> str:
    result = ""
    value = number
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _number(value: int | float) -> str:
    if isinstance(value, float) and not (float("-inf") < value < float("inf")):
        raise ValueError("constant binding must be finite")
    return json.dumps(value, allow_nan=False, separators=(",", ":"))


def _reject_extra_keys(payload: dict[str, Any], allowed: set[str], context: str, issues: list[str]) -> None:
    extras = sorted(set(payload) - allowed)
    if extras:
        issues.append(f"{context} contains undeclared fields: {extras}")


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in _FORBIDDEN_KEYS or _contains_forbidden_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _digest(payload: Any) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()
