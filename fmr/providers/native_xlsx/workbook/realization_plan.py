from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from fmr.providers.native_xlsx.workbook.content_plan import validate_workbook_content_plan_payload
from fmr.providers.native_xlsx.workbook.formula_specs import (
    WorkbookFormulaSpec,
    formula_spec_registry_payload,
    resolve_formula_spec,
)
from fmr.providers.native_xlsx.workbook.style_specs import (
    NUMBER_FORMAT_SPECS,
    STYLE_SPECS,
    semantic_type_for_slot,
    style_spec_registry_payload,
)

_PLAN_ID_RE = re.compile(r"^fmrr_[0-9a-f]{24}$")
_ALLOWED_STATUSES = {"blocked", "planned_realization", "reference_only", "satisfied_existing"}
_ALLOWED_CONTROLS = {
    "content_plan_pinned",
    "dependency_graph_checked",
    "formula_specs_pinned",
    "no_excel_formula_generation",
    "no_workbook_mutation",
    "source_hash_pinned",
    "style_specs_pinned",
    "styles_are_declarative",
}
_FORBIDDEN_KEYS = {
    "cell_write",
    "excel_formula",
    "macro",
    "script",
    "vba",
    "workbook_bytes",
}


def plan_workbook_realization(content_plan: dict[str, Any]) -> dict[str, Any]:
    content_issues = validate_workbook_content_plan_payload(content_plan)
    if content_issues:
        raise ValueError("invalid workbook content plan: " + "; ".join(content_issues))

    formula_registry = formula_spec_registry_payload()
    style_registry = style_spec_registry_payload()
    index = _build_identifier_index(content_plan)
    blockers: list[str] = []
    operation_realizations: list[dict[str, Any]] = []
    graph: dict[str, set[str]] = {}

    if not content_plan["ready_for_executor"]:
        blockers.extend(f"content_plan:{item}" for item in content_plan["blockers"])

    for operation in content_plan["operation_contents"]:
        operation_blockers: list[str] = []
        realized_slots: list[dict[str, Any]] = []
        source_status = operation["status"]

        if source_status == "blocked":
            status = "blocked"
            operation_blockers.extend(operation["blockers"] or ["content_plan_blocked"])
        elif source_status == "satisfied_existing":
            status = "satisfied_existing"
        elif source_status == "reference_only":
            status = "reference_only"
            for slot in operation["slots"]:
                realized_slots.append(_realize_reference_slot(slot))
        else:
            status = "planned_realization"
            for slot in operation["slots"]:
                realized, slot_blockers, edges = _realize_slot(
                    slot,
                    operation_id=operation["operation_id"],
                    index=index,
                )
                realized_slots.append(realized)
                operation_blockers.extend(slot_blockers)
                if edges:
                    graph.setdefault(_node_id(operation["operation_id"], slot["slot_id"]), set()).update(edges)
            if operation_blockers:
                status = "blocked"

        operation_realizations.append(
            {
                "sequence": operation["sequence"],
                "operation_id": operation["operation_id"],
                "source_operation": operation["source_operation"],
                "content_plan_status": source_status,
                "status": status,
                "title": operation["title"],
                "slots": realized_slots,
                "blockers": list(dict.fromkeys(operation_blockers)),
            }
        )
        blockers.extend(
            f"{operation['operation_id']}:{item}"
            for item in dict.fromkeys(operation_blockers)
        )

    cycle = _find_cycle(graph)
    if cycle:
        blockers.append("formula_dependency_cycle:" + "->".join(cycle))
    if not operation_realizations:
        blockers.append("no_realization_operations")

    deduplicated_blockers = tuple(dict.fromkeys(blockers))
    content_plan_sha256 = _digest(content_plan)
    controls = tuple(sorted(_ALLOWED_CONTROLS))
    provisional = {
        "contract_version": "workbook-realization-plan.v1",
        "content_plan_id": content_plan["content_plan_id"],
        "content_plan_sha256": content_plan_sha256,
        "formula_specs_sha256": formula_registry["registry_sha256"],
        "style_specs_sha256": style_registry["registry_sha256"],
        "expression_language": "fmr-expression.v1",
        "source": dict(content_plan["source"]),
        "ready_for_executor": not deduplicated_blockers,
        "execution_supported_by_this_release": False,
        "blockers": list(deduplicated_blockers),
        "operation_realizations": operation_realizations,
        "controls": list(controls),
    }
    return {
        **provisional,
        "realization_plan_id": f"fmrr_{_digest(provisional)[:24]}",
    }


def validate_workbook_realization_plan_payload(
    payload: Any,
    *,
    content_plan: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("realization plan must be an object",)
    _reject_extra_keys(
        payload,
        {
            "contract_version",
            "realization_plan_id",
            "content_plan_id",
            "content_plan_sha256",
            "formula_specs_sha256",
            "style_specs_sha256",
            "expression_language",
            "source",
            "ready_for_executor",
            "execution_supported_by_this_release",
            "blockers",
            "operation_realizations",
            "controls",
        },
        "realization plan",
        issues,
    )
    if payload.get("contract_version") != "workbook-realization-plan.v1":
        issues.append("unsupported contract_version")
    if payload.get("expression_language") != "fmr-expression.v1":
        issues.append("unsupported expression_language")
    if _contains_forbidden_key(payload):
        issues.append("realization plan contains forbidden workbook execution fields")

    plan_id = payload.get("realization_plan_id")
    if not isinstance(plan_id, str) or not _PLAN_ID_RE.fullmatch(plan_id):
        issues.append("realization_plan_id is invalid")
    for field in (
        "content_plan_id",
        "content_plan_sha256",
        "formula_specs_sha256",
        "style_specs_sha256",
    ):
        if not isinstance(payload.get(field), str) or not payload.get(field):
            issues.append(f"{field} must be a non-empty string")
    for field in ("content_plan_sha256", "formula_specs_sha256", "style_specs_sha256"):
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

    operations = payload.get("operation_realizations")
    if not isinstance(operations, list):
        issues.append("operation_realizations must be an array")
    else:
        _validate_operation_realizations(operations, issues)

    controls = payload.get("controls")
    if not _is_string_list(controls):
        issues.append("controls must be an array of strings")
    elif set(controls) != _ALLOWED_CONTROLS or len(controls) != len(_ALLOWED_CONTROLS):
        issues.append("controls do not match the required control set")

    formula_registry = formula_spec_registry_payload()
    style_registry = style_spec_registry_payload()
    if payload.get("formula_specs_sha256") != formula_registry["registry_sha256"]:
        issues.append("formula_specs_sha256 does not match the current registry")
    if payload.get("style_specs_sha256") != style_registry["registry_sha256"]:
        issues.append("style_specs_sha256 does not match the current registry")

    if isinstance(plan_id, str) and _PLAN_ID_RE.fullmatch(plan_id):
        candidate = dict(payload)
        candidate.pop("realization_plan_id", None)
        expected = f"fmrr_{_digest(candidate)[:24]}"
        if plan_id != expected:
            issues.append("realization_plan_id does not match payload")

    if content_plan is not None:
        try:
            expected_payload = plan_workbook_realization(content_plan)
        except ValueError as exc:
            issues.append(f"deterministic recomputation failed: {exc}")
        else:
            if payload != expected_payload:
                issues.append("realization plan does not match deterministic recomputation")

    return tuple(dict.fromkeys(issues))


def _realize_slot(
    slot: dict[str, Any],
    *,
    operation_id: str,
    index: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[str], set[str]]:
    blockers: list[str] = []
    edges: set[str] = set()
    formula_binding: dict[str, Any] | None = None
    formula_spec: WorkbookFormulaSpec | None = None

    if slot["content_kind"] in {"formula_identifier", "validation_identifier"}:
        identifier = slot.get("identifier")
        if not isinstance(identifier, str):
            blockers.append(f"formula_identifier_missing:{slot['slot_id']}")
        else:
            try:
                formula_spec = resolve_formula_spec(identifier)
            except KeyError:
                blockers.append(f"formula_spec_missing:{identifier}")
            else:
                dependency_bindings: list[dict[str, Any]] = []
                for dependency in formula_spec.dependencies:
                    binding, issue = _resolve_dependency(
                        dependency.to_dict(),
                        slot=slot,
                        operation_id=operation_id,
                        index=index,
                    )
                    dependency_bindings.append(binding)
                    if issue:
                        blockers.append(issue)
                    target = binding.get("target")
                    if (
                        binding.get("binding_type") == "content_slot"
                        and isinstance(target, dict)
                        and target.get("content_kind") in {"formula_identifier", "validation_identifier"}
                    ):
                        edges.add(_node_id(target["operation_id"], target["slot_id"]))
                formula_binding = {
                    "resolved_identifier": identifier,
                    "formula_spec_ref": formula_spec.specification_ref,
                    "formula_kind": formula_spec.formula_kind,
                    "expression_language": "fmr-expression.v1",
                    "expression_template": formula_spec.expression_template,
                    "dependencies": dependency_bindings,
                    "output_type": formula_spec.output_type,
                    "sign_convention": formula_spec.sign_convention,
                    "fill_policy": formula_spec.fill_policy,
                    "circularity_policy": formula_spec.circularity_policy,
                }

    style_binding: dict[str, Any] | None = None
    if slot.get("coordinate") is not None:
        try:
            semantic_type = semantic_type_for_slot(
                slot,
                formula_output_type=formula_spec.output_type if formula_spec else None,
            )
            role = STYLE_SPECS[slot["format_role"]]
            number_format = NUMBER_FORMAT_SPECS[semantic_type]
        except (KeyError, ValueError) as exc:
            blockers.append(f"style_resolution_failed:{slot['slot_id']}:{exc}")
        else:
            role_payload = role.to_dict()
            role_payload["protection"] = {
                "locked": False if slot.get("editable") is True else role.locked
            }
            style_binding = {
                "style_spec_ref": role.specification_ref,
                "number_format_spec_ref": number_format.specification_ref,
                "semantic_type": semantic_type,
                "role_style": role_payload,
                "number_format": number_format.to_dict(),
            }

    return (
        {
            "slot_id": slot["slot_id"],
            "sheet_name": slot["sheet_name"],
            "sheet_position": slot["sheet_position"],
            "coordinate": slot["coordinate"],
            "content_kind": slot["content_kind"],
            "label": slot["label"],
            "identifier": slot["identifier"],
            "editable": slot["editable"],
            "formula_binding": formula_binding,
            "style_binding": style_binding,
        },
        blockers,
        edges,
    )


def _realize_reference_slot(slot: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot_id": slot["slot_id"],
        "sheet_name": None,
        "sheet_position": None,
        "coordinate": None,
        "content_kind": slot["content_kind"],
        "label": slot["label"],
        "identifier": slot["identifier"],
        "editable": slot["editable"],
        "formula_binding": None,
        "style_binding": None,
        "reference_binding": {
            "binding_type": "reference_target",
            "identifier": slot["identifier"],
        },
    }


def _build_identifier_index(content_plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for operation in content_plan["operation_contents"]:
        for slot in operation["slots"]:
            identifier = slot.get("identifier")
            if not isinstance(identifier, str):
                continue
            index.setdefault(identifier, []).append(
                {
                    "operation_id": operation["operation_id"],
                    "source_operation": operation["source_operation"],
                    "slot_id": slot["slot_id"],
                    "sheet_name": slot["sheet_name"],
                    "sheet_position": slot["sheet_position"],
                    "coordinate": slot["coordinate"],
                    "content_kind": slot["content_kind"],
                }
            )
    return index


def _resolve_dependency(
    dependency: dict[str, Any],
    *,
    slot: dict[str, Any],
    operation_id: str,
    index: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], str | None]:
    source = dependency["source"]
    if source != "content_slot":
        return (
            {
                "name": dependency["name"],
                "binding_type": source,
                "identifier": dependency["identifier"],
                "required": dependency["required"],
                "target": None,
            },
            None,
        )

    candidates = list(index.get(dependency["identifier"], ()))
    if not candidates:
        issue = None if not dependency["required"] else f"dependency_missing:{dependency['identifier']}"
        return (
            {
                "name": dependency["name"],
                "binding_type": "content_slot",
                "identifier": dependency["identifier"],
                "required": dependency["required"],
                "target": None,
            },
            issue,
        )

    allocation_prefix = _allocation_prefix(slot["slot_id"])
    ranked_groups = (
        [
            item
            for item in candidates
            if item["operation_id"] == operation_id
            and _allocation_prefix(item["slot_id"]) == allocation_prefix
            and item["sheet_name"] == slot["sheet_name"]
        ],
        [
            item
            for item in candidates
            if item["operation_id"] == operation_id and item["sheet_name"] == slot["sheet_name"]
        ],
        [item for item in candidates if item["operation_id"] == operation_id],
        candidates,
    )
    selected_group = next((group for group in ranked_groups if group), [])
    unique = _deduplicate_targets(selected_group)
    if len(unique) != 1:
        return (
            {
                "name": dependency["name"],
                "binding_type": "content_slot",
                "identifier": dependency["identifier"],
                "required": dependency["required"],
                "target": None,
            },
            f"dependency_ambiguous:{dependency['identifier']}",
        )
    return (
        {
            "name": dependency["name"],
            "binding_type": "content_slot",
            "identifier": dependency["identifier"],
            "required": dependency["required"],
            "target": unique[0],
        },
        None,
    )


def _deduplicate_targets(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = (
            item["operation_id"],
            item["slot_id"],
            item["sheet_name"],
            item["coordinate"],
        )
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _allocation_prefix(slot_id: str) -> str:
    prefix, separator, _ = slot_id.partition("_")
    return prefix if separator and re.fullmatch(r"a[1-9][0-9]*", prefix) else ""


def _node_id(operation_id: str, slot_id: str) -> str:
    return f"{operation_id}:{slot_id}"


def _find_cycle(graph: dict[str, set[str]]) -> tuple[str, ...]:
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> tuple[str, ...]:
        if node in visiting:
            start = visiting.index(node)
            return tuple(visiting[start:] + [node])
        if node in visited:
            return ()
        visiting.append(node)
        for dependency in sorted(graph.get(node, ())):
            cycle = visit(dependency)
            if cycle:
                return cycle
        visiting.pop()
        visited.add(node)
        return ()

    for node in sorted(graph):
        cycle = visit(node)
        if cycle:
            return cycle
    return ()


def _validate_operation_realizations(operations: list[Any], issues: list[str]) -> None:
    seen: set[str] = set()
    for index, operation in enumerate(operations):
        context = f"operation_realizations[{index}]"
        if not isinstance(operation, dict):
            issues.append(f"{context} must be an object")
            continue
        _reject_extra_keys(
            operation,
            {
                "sequence",
                "operation_id",
                "source_operation",
                "content_plan_status",
                "status",
                "title",
                "slots",
                "blockers",
            },
            context,
            issues,
        )
        operation_id = operation.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            issues.append(f"{context}.operation_id must be a non-empty string")
        elif operation_id in seen:
            issues.append(f"duplicate operation_id: {operation_id}")
        else:
            seen.add(operation_id)
        if operation.get("status") not in _ALLOWED_STATUSES:
            issues.append(f"{context}.status is invalid")
        if not isinstance(operation.get("slots"), list):
            issues.append(f"{context}.slots must be an array")
        if not _is_string_list(operation.get("blockers")):
            issues.append(f"{context}.blockers must be an array of strings")


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in _FORBIDDEN_KEYS or _contains_forbidden_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _reject_extra_keys(
    payload: dict[str, Any],
    allowed: set[str],
    context: str,
    issues: list[str],
) -> None:
    extras = sorted(set(payload) - allowed)
    if extras:
        issues.append(f"{context} contains undeclared fields: {extras}")


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _digest(payload: Any) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()
