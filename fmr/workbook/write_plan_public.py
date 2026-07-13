from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from fmr.workbook.write_plan import (
    compile_workbook_write_plan as _compile_unordered,
    validate_workbook_write_context_payload,
    validate_workbook_write_plan_payload as _validate_structure,
)


def compile_workbook_write_plan(
    realization_plan: dict[str, Any],
    write_context: dict[str, Any],
) -> dict[str, Any]:
    normalized_realization = _normalize_deferred_bindings(realization_plan)
    payload = _compile_unordered(normalized_realization, write_context)
    payload["realization_plan_sha256"] = _digest(realization_plan)
    sequence = 0
    for phase in payload["phases"]:
        for record in phase["records"]:
            sequence += 1
            record["sequence"] = sequence
            record["record_id"] = f"fmrw_{sequence:06d}"
    payload["write_record_count"] = sequence
    payload.pop("write_plan_id", None)
    payload["write_plan_id"] = f"fmrw_{_digest(payload)[:24]}"
    return payload


def validate_workbook_write_plan_payload(
    payload: Any,
    *,
    realization_plan: dict[str, Any] | None = None,
    write_context: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    issues = list(_validate_structure(payload))
    if isinstance(payload, dict):
        _validate_source(payload.get("source"), issues)
        _validate_phase_payloads(payload.get("phases"), issues)
    if realization_plan is not None and write_context is not None:
        try:
            expected = compile_workbook_write_plan(realization_plan, write_context)
        except ValueError as exc:
            issues.append(f"deterministic recomputation failed: {exc}")
        else:
            if payload != expected:
                issues.append("write plan does not match deterministic recomputation")
    return tuple(dict.fromkeys(issues))


def _normalize_deferred_bindings(realization_plan: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(realization_plan)
    for operation in normalized.get("operation_realizations", []):
        for slot in operation.get("slots", []):
            formula = slot.get("formula_binding")
            if not isinstance(formula, dict):
                continue
            for dependency in formula.get("dependencies", []):
                if (
                    isinstance(dependency, dict)
                    and dependency.get("binding_type") == "period_context"
                    and dependency.get("target") is None
                ):
                    dependency["target"] = {}
    return normalized


def _validate_source(value: Any, issues: list[str]) -> None:
    if not isinstance(value, dict):
        issues.append("source must be an object")
        return
    extras = sorted(set(value) - {"filename", "sha256", "size_bytes"})
    if extras:
        issues.append(f"source contains undeclared fields: {extras}")
    if not isinstance(value.get("filename"), str) or not value.get("filename"):
        issues.append("source.filename must be a non-empty string")
    sha = value.get("sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(character not in "0123456789abcdef" for character in sha):
        issues.append("source.sha256 must be a SHA-256 hex string")
    if not isinstance(value.get("size_bytes"), int) or value.get("size_bytes") < 0:
        issues.append("source.size_bytes must be a non-negative integer")


def _validate_phase_payloads(value: Any, issues: list[str]) -> None:
    if not isinstance(value, list):
        return
    expected_names = {
        10: "sheet_setup",
        20: "values_and_inputs",
        30: "formulas_and_validations",
        40: "styles_and_protection",
    }
    for phase_index, phase in enumerate(value):
        if not isinstance(phase, dict):
            continue
        phase_number = phase.get("phase")
        if phase.get("name") != expected_names.get(phase_number):
            issues.append(f"phases[{phase_index}].name does not match phase")
        records = phase.get("records")
        if not isinstance(records, list):
            continue
        for record_index, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            context = f"phases[{phase_index}].records[{record_index}]"
            record_payload = record.get("payload")
            if not isinstance(record_payload, dict):
                continue
            write_kind = record.get("write_kind")
            if write_kind == "ensure_sheet":
                _expect_keys(record_payload, {"mode", "position"}, context, issues)
                if record_payload.get("mode") != "ensure":
                    issues.append(f"{context}.payload.mode must be ensure")
                if not isinstance(record_payload.get("position"), int):
                    issues.append(f"{context}.payload.position must be an integer")
            elif write_kind == "write_value":
                _expect_keys(record_payload, {"value_type", "value"}, context, issues)
                if record_payload.get("value_type") != "string" or not isinstance(record_payload.get("value"), str):
                    issues.append(f"{context}.payload must contain a string value")
            elif write_kind == "reserve_input":
                _expect_keys(record_payload, {"value_type", "editable"}, context, issues)
                if record_payload != {"value_type": "blank", "editable": True}:
                    issues.append(f"{context}.payload must reserve a blank editable input")
            elif write_kind == "write_formula":
                _expect_keys(
                    record_payload,
                    {"formula", "formula_identifier", "output_type", "sign_convention"},
                    context,
                    issues,
                )
                formula = record_payload.get("formula")
                if isinstance(formula, str):
                    lowered = formula.lower()
                    if any(marker in formula for marker in ("[", "]", "{{", "}}")):
                        issues.append(f"{context}.payload.formula contains forbidden reference syntax")
                    if any(marker in lowered for marker in ("http://", "https://", "file://", "dde(")):
                        issues.append(f"{context}.payload.formula contains an external reference")
                for field in ("formula_identifier", "output_type", "sign_convention"):
                    if not isinstance(record_payload.get(field), str) or not record_payload.get(field):
                        issues.append(f"{context}.payload.{field} must be a non-empty string")
            elif write_kind == "apply_style":
                _expect_keys(record_payload, {"style"}, context, issues)
                if not isinstance(record_payload.get("style"), dict):
                    issues.append(f"{context}.payload.style must be an object")


def _expect_keys(
    payload: dict[str, Any],
    allowed: set[str],
    context: str,
    issues: list[str],
) -> None:
    extras = sorted(set(payload) - allowed)
    missing = sorted(allowed - set(payload))
    if extras:
        issues.append(f"{context}.payload contains undeclared fields: {extras}")
    if missing:
        issues.append(f"{context}.payload is missing fields: {missing}")


def _digest(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()
