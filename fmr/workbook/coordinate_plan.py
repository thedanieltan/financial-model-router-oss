from __future__ import annotations

import hashlib
import json
import re
import string
from dataclasses import dataclass
from typing import Any

from fmr.workbook.analyse import WorkbookAnalysis
from fmr.workbook.coordinate_rules import (
    COORDINATE_RULES,
    coordinate_rule_registry_payload,
)
from fmr.workbook.target_resolution import (
    resolve_workbook_patch_targets,
    validate_workbook_target_resolution_payload,
)

_MAX_ROW = 1_048_576
_MAX_COLUMN = 16_384
_PLAN_ID_RE = re.compile(r"^fmrc_[0-9a-f]{24}$")
_RANGE_RE = re.compile(r"^([A-Z]{1,3})([1-9][0-9]*):([A-Z]{1,3})([1-9][0-9]*)$")
_ALLOWED_STATUSES = {
    "blocked",
    "planned_column_extension",
    "planned_new_sheet",
    "planned_range",
    "reference_only",
    "satisfied_existing",
}
_ALLOWED_CONTROLS = {
    "collision_checks_required",
    "coordinate_planning_only",
    "coordinate_rules_pinned",
    "excel_bounds_checked",
    "no_formula_generation",
    "no_workbook_mutation",
    "source_hash_pinned",
    "target_resolution_pinned",
}
_FORBIDDEN_KEYS = {
    "cell_write",
    "formula",
    "macro",
    "script",
    "vba",
    "workbook_bytes",
}


@dataclass(frozen=True)
class Rectangle:
    start_row: int
    start_column: int
    end_row: int
    end_column: int

    @property
    def row_count(self) -> int:
        return self.end_row - self.start_row + 1

    @property
    def column_count(self) -> int:
        return self.end_column - self.start_column + 1

    @property
    def a1_range(self) -> str:
        return (
            f"{_column_name(self.start_column)}{self.start_row}:"
            f"{_column_name(self.end_column)}{self.end_row}"
        )

    def overlaps(self, other: "Rectangle") -> bool:
        return not (
            self.end_row < other.start_row
            or other.end_row < self.start_row
            or self.end_column < other.start_column
            or other.end_column < self.start_column
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "range": self.a1_range,
            "start": {"row": self.start_row, "column": self.start_column},
            "end": {"row": self.end_row, "column": self.end_column},
            "rows": self.row_count,
            "columns": self.column_count,
        }


def plan_workbook_coordinates(
    analysis: WorkbookAnalysis,
    patch: dict[str, Any],
    target_resolution: dict[str, Any],
    *,
    forecast_period_count: int,
) -> dict[str, Any]:
    if not isinstance(forecast_period_count, int) or isinstance(
        forecast_period_count, bool
    ):
        raise ValueError("forecast_period_count must be an integer")
    if not 1 <= forecast_period_count <= 60:
        raise ValueError("forecast_period_count must be between 1 and 60")

    resolution_issues = validate_workbook_target_resolution_payload(
        target_resolution,
        analysis=analysis,
        patch=patch,
    )
    if resolution_issues:
        raise ValueError(
            "invalid workbook target resolution: " + "; ".join(resolution_issues)
        )
    expected_resolution = resolve_workbook_patch_targets(analysis, patch).to_dict()
    if target_resolution != expected_resolution:
        raise ValueError(
            "workbook target resolution does not match deterministic recomputation"
        )

    registry = coordinate_rule_registry_payload()
    source_positions = {
        sheet.name: sheet.position for sheet in analysis.workbook_map.sheets
    }
    occupied: dict[str, list[Rectangle]] = {}
    source_used_ranges: dict[str, str | None] = {}
    for sheet in analysis.workbook_map.sheets:
        source_used_ranges[sheet.name] = sheet.used_range
        occupied[sheet.name] = []
        if sheet.used_range:
            occupied[sheet.name].append(_parse_range(sheet.used_range))

    planned_positions: dict[str, int] = {}
    next_position = analysis.workbook_map.sheet_count + 1
    operation_plans: list[dict[str, Any]] = []
    blockers: list[str] = []

    if not target_resolution["ready_for_executor"]:
        blockers.extend(
            f"target_resolution:{item}" for item in target_resolution["blockers"]
        )

    for item in target_resolution["resolutions"]:
        operation_id = item["operation_id"]
        source_operation = item["source_operation"]
        rule = COORDINATE_RULES[source_operation]
        target = item["target"]
        sheet_names = list(target["sheet_names"])
        operation_blockers: list[str] = []
        allocations: list[dict[str, Any]] = []

        if item["status"] == "blocked":
            operation_blockers.extend(item["blockers"] or ["target_resolution_blocked"])
            status = "blocked"
        elif rule.allocation_kind == "reference_only":
            status = "reference_only"
        elif rule.allocation_kind == "sheet_block":
            status, allocations, operation_blockers, next_position = _plan_sheet_block(
                item=item,
                rule=rule,
                sheet_names=sheet_names,
                source_positions=source_positions,
                source_used_ranges=source_used_ranges,
                occupied=occupied,
                planned_positions=planned_positions,
                next_position=next_position,
            )
        elif rule.allocation_kind == "append_block":
            status, allocations, operation_blockers, next_position = _plan_append_block(
                item=item,
                rule=rule,
                sheet_names=sheet_names,
                source_positions=source_positions,
                source_used_ranges=source_used_ranges,
                occupied=occupied,
                planned_positions=planned_positions,
                next_position=next_position,
            )
        elif rule.allocation_kind == "column_extension":
            status, allocations, operation_blockers = _plan_column_extension(
                sheet_names=sheet_names,
                source_positions=source_positions,
                source_used_ranges=source_used_ranges,
                occupied=occupied,
                forecast_period_count=forecast_period_count,
            )
        else:
            status = "blocked"
            operation_blockers.append(
                f"unsupported_allocation_kind:{rule.allocation_kind}"
            )

        operation_plans.append(
            {
                "sequence": item["sequence"],
                "operation_id": operation_id,
                "source_operation": source_operation,
                "specification_ref": item["specification_ref"],
                "coordinate_rule_ref": rule.specification_ref,
                "semantic_role": item["semantic_role"],
                "status": status,
                "target_status": item["status"],
                "allocations": allocations,
                "evidence": list(item["evidence"]),
                "blockers": list(dict.fromkeys(operation_blockers)),
            }
        )
        blockers.extend(
            f"{operation_id}:{blocker}"
            for blocker in dict.fromkeys(operation_blockers)
        )

    sheet_plan = _build_sheet_plan(
        analysis=analysis,
        planned_positions=planned_positions,
        source_used_ranges=source_used_ranges,
        operation_plans=operation_plans,
    )
    deduplicated_blockers = tuple(dict.fromkeys(blockers))
    target_resolution_sha256 = _digest(target_resolution)
    controls = tuple(sorted(_ALLOWED_CONTROLS))
    provisional = {
        "contract_version": "workbook-coordinate-plan.v1",
        "patch_id": patch["patch_id"],
        "resolution_id": target_resolution["resolution_id"],
        "target_resolution_sha256": target_resolution_sha256,
        "coordinate_rules_sha256": registry["registry_sha256"],
        "source": dict(patch["source"]),
        "layout_parameters": {
            "forecast_period_count": forecast_period_count,
        },
        "ready_for_executor": not deduplicated_blockers,
        "execution_supported_by_this_release": False,
        "blockers": list(deduplicated_blockers),
        "operation_plans": operation_plans,
        "sheet_plan": sheet_plan,
        "controls": list(controls),
    }
    return {
        **provisional,
        "coordinate_plan_id": f"fmrc_{_digest(provisional)[:24]}",
    }


def validate_workbook_coordinate_plan_payload(
    payload: Any,
    *,
    analysis: WorkbookAnalysis | None = None,
    patch: dict[str, Any] | None = None,
    target_resolution: dict[str, Any] | None = None,
    forecast_period_count: int | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("coordinate plan must be an object",)
    allowed_top = {
        "contract_version",
        "coordinate_plan_id",
        "patch_id",
        "resolution_id",
        "target_resolution_sha256",
        "coordinate_rules_sha256",
        "source",
        "layout_parameters",
        "ready_for_executor",
        "execution_supported_by_this_release",
        "blockers",
        "operation_plans",
        "sheet_plan",
        "controls",
    }
    _reject_extra_keys(payload, allowed_top, "coordinate plan", issues)
    if payload.get("contract_version") != "workbook-coordinate-plan.v1":
        issues.append("unsupported contract_version")
    if _contains_forbidden_key(payload):
        issues.append("coordinate plan contains executable workbook fields")

    plan_id = payload.get("coordinate_plan_id")
    if not isinstance(plan_id, str) or not _PLAN_ID_RE.fullmatch(plan_id):
        issues.append("coordinate_plan_id is invalid")
    for field in (
        "patch_id",
        "resolution_id",
        "target_resolution_sha256",
        "coordinate_rules_sha256",
    ):
        if not isinstance(payload.get(field), str) or not payload.get(field):
            issues.append(f"{field} must be a non-empty string")
    for field in ("target_resolution_sha256", "coordinate_rules_sha256"):
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

    layout = payload.get("layout_parameters")
    if not isinstance(layout, dict):
        issues.append("layout_parameters must be an object")
    else:
        _reject_extra_keys(
            layout,
            {"forecast_period_count"},
            "layout_parameters",
            issues,
        )
        count = layout.get("forecast_period_count")
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or not 1 <= count <= 60
        ):
            issues.append("forecast_period_count must be between 1 and 60")

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

    operation_plans = payload.get("operation_plans")
    if not isinstance(operation_plans, list):
        issues.append("operation_plans must be an array")
    else:
        _validate_operation_plans(operation_plans, issues)

    sheet_plan = payload.get("sheet_plan")
    if not isinstance(sheet_plan, list):
        issues.append("sheet_plan must be an array")
    else:
        _validate_sheet_plan(sheet_plan, issues)

    controls = payload.get("controls")
    if not _is_string_list(controls):
        issues.append("controls must be an array of strings")
    elif set(controls) != _ALLOWED_CONTROLS or len(controls) != len(_ALLOWED_CONTROLS):
        issues.append("controls do not match the required control set")

    if isinstance(plan_id, str) and _PLAN_ID_RE.fullmatch(plan_id):
        candidate = dict(payload)
        candidate.pop("coordinate_plan_id", None)
        expected = f"fmrc_{_digest(candidate)[:24]}"
        if plan_id != expected:
            issues.append("coordinate_plan_id does not match payload")

    if (
        analysis is not None
        and patch is not None
        and target_resolution is not None
        and forecast_period_count is not None
    ):
        try:
            expected_payload = plan_workbook_coordinates(
                analysis,
                patch,
                target_resolution,
                forecast_period_count=forecast_period_count,
            )
        except ValueError as exc:
            issues.append(f"deterministic recomputation failed: {exc}")
        else:
            if payload != expected_payload:
                issues.append(
                    "coordinate plan does not match deterministic recomputation"
                )

    return tuple(dict.fromkeys(issues))


def _plan_sheet_block(
    *,
    item: dict[str, Any],
    rule: Any,
    sheet_names: list[str],
    source_positions: dict[str, int],
    source_used_ranges: dict[str, str | None],
    occupied: dict[str, list[Rectangle]],
    planned_positions: dict[str, int],
    next_position: int,
) -> tuple[str, list[dict[str, Any]], list[str], int]:
    if len(sheet_names) != 1:
        return "blocked", [], ["sheet_block_requires_one_sheet"], next_position
    sheet_name = sheet_names[0]
    if item["status"] == "resolved_existing" and rule.existing_target_mode == "satisfied":
        return "satisfied_existing", [], [], next_position
    position, state, next_position = _ensure_sheet_state(
        sheet_name,
        source_positions,
        source_used_ranges,
        occupied,
        planned_positions,
        next_position,
    )
    rectangle = Rectangle(1, 1, rule.rows, rule.columns)
    collision = _first_collision(rectangle, occupied[sheet_name])
    if collision:
        return (
            "blocked",
            [],
            [f"coordinate_collision:{sheet_name}:{collision.a1_range}"],
            next_position,
        )
    allocation = _allocation(
        sheet_name=sheet_name,
        sheet_state=state,
        sheet_position=position,
        rectangle=rectangle,
        placement="sheet_origin",
        occupied_before=occupied[sheet_name],
    )
    occupied[sheet_name].append(rectangle)
    return "planned_new_sheet", [allocation], [], next_position


def _plan_append_block(
    *,
    item: dict[str, Any],
    rule: Any,
    sheet_names: list[str],
    source_positions: dict[str, int],
    source_used_ranges: dict[str, str | None],
    occupied: dict[str, list[Rectangle]],
    planned_positions: dict[str, int],
    next_position: int,
) -> tuple[str, list[dict[str, Any]], list[str], int]:
    if not sheet_names:
        return "blocked", [], ["append_block_requires_target_sheet"], next_position
    allocations: list[dict[str, Any]] = []
    blockers: list[str] = []
    for sheet_name in sheet_names:
        position, state, next_position = _ensure_sheet_state(
            sheet_name,
            source_positions,
            source_used_ranges,
            occupied,
            planned_positions,
            next_position,
        )
        if occupied[sheet_name]:
            max_end_row = max(
                rectangle.end_row for rectangle in occupied[sheet_name]
            )
            start_row = max_end_row + rule.gap_rows + 1
        else:
            start_row = 1
        rectangle = Rectangle(
            start_row,
            1,
            start_row + rule.rows - 1,
            rule.columns,
        )
        bounds_issue = _bounds_issue(rectangle)
        if bounds_issue:
            blockers.append(f"{sheet_name}:{bounds_issue}")
            continue
        collision = _first_collision(rectangle, occupied[sheet_name])
        if collision:
            blockers.append(
                f"coordinate_collision:{sheet_name}:{collision.a1_range}"
            )
            continue
        allocation = _allocation(
            sheet_name=sheet_name,
            sheet_state=state,
            sheet_position=position,
            rectangle=rectangle,
            placement="append_below_occupied_range",
            occupied_before=occupied[sheet_name],
        )
        occupied[sheet_name].append(rectangle)
        allocations.append(allocation)
    if blockers:
        return "blocked", allocations, blockers, next_position
    return "planned_range", allocations, [], next_position


def _plan_column_extension(
    *,
    sheet_names: list[str],
    source_positions: dict[str, int],
    source_used_ranges: dict[str, str | None],
    occupied: dict[str, list[Rectangle]],
    forecast_period_count: int,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    if not sheet_names:
        return "blocked", [], ["column_extension_requires_target_sheets"]
    allocations: list[dict[str, Any]] = []
    blockers: list[str] = []
    for sheet_name in sheet_names:
        used_range = source_used_ranges.get(sheet_name)
        if not used_range:
            blockers.append(f"missing_used_range:{sheet_name}")
            continue
        source_rectangle = _parse_range(used_range)
        max_end_column = max(
            (rectangle.end_column for rectangle in occupied[sheet_name]),
            default=source_rectangle.end_column,
        )
        rectangle = Rectangle(
            source_rectangle.start_row,
            max_end_column + 1,
            source_rectangle.end_row,
            max_end_column + forecast_period_count,
        )
        bounds_issue = _bounds_issue(rectangle)
        if bounds_issue:
            blockers.append(f"{sheet_name}:{bounds_issue}")
            continue
        collision = _first_collision(rectangle, occupied[sheet_name])
        if collision:
            blockers.append(
                f"coordinate_collision:{sheet_name}:{collision.a1_range}"
            )
            continue
        allocation = _allocation(
            sheet_name=sheet_name,
            sheet_state="existing",
            sheet_position=source_positions[sheet_name],
            rectangle=rectangle,
            placement="append_right_of_occupied_range",
            occupied_before=occupied[sheet_name],
        )
        occupied[sheet_name].append(rectangle)
        allocations.append(allocation)
    if blockers:
        return "blocked", allocations, blockers
    return "planned_column_extension", allocations, []


def _ensure_sheet_state(
    sheet_name: str,
    source_positions: dict[str, int],
    source_used_ranges: dict[str, str | None],
    occupied: dict[str, list[Rectangle]],
    planned_positions: dict[str, int],
    next_position: int,
) -> tuple[int, str, int]:
    if sheet_name in source_positions:
        return source_positions[sheet_name], "existing", next_position
    if sheet_name not in planned_positions:
        if len(sheet_name) > 31 or any(character in sheet_name for character in "[]:*?/\\"):
            raise ValueError(f"invalid planned sheet name: {sheet_name}")
        planned_positions[sheet_name] = next_position
        source_used_ranges[sheet_name] = None
        occupied[sheet_name] = []
        next_position += 1
    return planned_positions[sheet_name], "planned", next_position


def _allocation(
    *,
    sheet_name: str,
    sheet_state: str,
    sheet_position: int,
    rectangle: Rectangle,
    placement: str,
    occupied_before: list[Rectangle],
) -> dict[str, Any]:
    bounds_issue = _bounds_issue(rectangle)
    if bounds_issue:
        raise ValueError(bounds_issue)
    return {
        "sheet_name": sheet_name,
        "sheet_state": sheet_state,
        "sheet_position": sheet_position,
        "placement": placement,
        **rectangle.to_dict(),
        "occupied_before": [
            existing.a1_range for existing in occupied_before
        ],
        "collision_checked": True,
    }


def _build_sheet_plan(
    *,
    analysis: WorkbookAnalysis,
    planned_positions: dict[str, int],
    source_used_ranges: dict[str, str | None],
    operation_plans: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_sheet: dict[str, list[str]] = {}
    for operation in operation_plans:
        for allocation in operation["allocations"]:
            by_sheet.setdefault(allocation["sheet_name"], []).append(
                allocation["range"]
            )
    existing_names = {sheet.name for sheet in analysis.workbook_map.sheets}
    position_map = {
        sheet.name: sheet.position for sheet in analysis.workbook_map.sheets
    }
    position_map.update(planned_positions)
    names = sorted(by_sheet, key=lambda name: (position_map[name], name))
    return [
        {
            "sheet_name": name,
            "sheet_state": "existing" if name in existing_names else "planned",
            "sheet_position": position_map[name],
            "source_used_range": source_used_ranges.get(name),
            "planned_ranges": by_sheet[name],
        }
        for name in names
    ]


def _validate_operation_plans(
    operation_plans: list[Any],
    issues: list[str],
) -> None:
    seen_ids: set[str] = set()
    for index, operation in enumerate(operation_plans):
        path = f"operation_plans[{index}]"
        if not isinstance(operation, dict):
            issues.append(f"{path} must be an object")
            continue
        expected_keys = {
            "sequence",
            "operation_id",
            "source_operation",
            "specification_ref",
            "coordinate_rule_ref",
            "semantic_role",
            "status",
            "target_status",
            "allocations",
            "evidence",
            "blockers",
        }
        _reject_extra_keys(operation, expected_keys, path, issues)
        if operation.get("sequence") != index + 1:
            issues.append(f"{path}.sequence must equal {index + 1}")
        operation_id = operation.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            issues.append(f"{path}.operation_id must be a non-empty string")
        elif operation_id in seen_ids:
            issues.append(f"{path}.operation_id is duplicated")
        else:
            seen_ids.add(operation_id)
        if operation.get("status") not in _ALLOWED_STATUSES:
            issues.append(f"{path}.status is invalid")
        allocations = operation.get("allocations")
        if not isinstance(allocations, list):
            issues.append(f"{path}.allocations must be an array")
        else:
            for allocation_index, allocation in enumerate(allocations):
                _validate_allocation(
                    allocation,
                    f"{path}.allocations[{allocation_index}]",
                    issues,
                )
        for field in ("evidence", "blockers"):
            if not _is_string_list(operation.get(field)):
                issues.append(f"{path}.{field} must be an array of strings")


def _validate_allocation(
    allocation: Any,
    path: str,
    issues: list[str],
) -> None:
    if not isinstance(allocation, dict):
        issues.append(f"{path} must be an object")
        return
    expected_keys = {
        "sheet_name",
        "sheet_state",
        "sheet_position",
        "placement",
        "range",
        "start",
        "end",
        "rows",
        "columns",
        "occupied_before",
        "collision_checked",
    }
    _reject_extra_keys(allocation, expected_keys, path, issues)
    if not isinstance(allocation.get("sheet_name"), str) or not allocation.get(
        "sheet_name"
    ):
        issues.append(f"{path}.sheet_name must be a non-empty string")
    if allocation.get("sheet_state") not in {"existing", "planned"}:
        issues.append(f"{path}.sheet_state is invalid")
    if not isinstance(allocation.get("sheet_position"), int) or allocation.get(
        "sheet_position"
    ) < 1:
        issues.append(f"{path}.sheet_position must be positive")
    coordinate_range = allocation.get("range")
    if not isinstance(coordinate_range, str):
        issues.append(f"{path}.range must be a string")
        return
    try:
        rectangle = _parse_range(coordinate_range)
    except ValueError:
        issues.append(f"{path}.range is invalid")
        return
    if allocation.get("start") != {
        "row": rectangle.start_row,
        "column": rectangle.start_column,
    }:
        issues.append(f"{path}.start does not match range")
    if allocation.get("end") != {
        "row": rectangle.end_row,
        "column": rectangle.end_column,
    }:
        issues.append(f"{path}.end does not match range")
    if allocation.get("rows") != rectangle.row_count:
        issues.append(f"{path}.rows does not match range")
    if allocation.get("columns") != rectangle.column_count:
        issues.append(f"{path}.columns does not match range")
    if not _is_string_list(allocation.get("occupied_before")):
        issues.append(f"{path}.occupied_before must be an array of strings")
    if allocation.get("collision_checked") is not True:
        issues.append(f"{path}.collision_checked must be true")


def _validate_sheet_plan(sheet_plan: list[Any], issues: list[str]) -> None:
    seen_positions: set[int] = set()
    for index, item in enumerate(sheet_plan):
        path = f"sheet_plan[{index}]"
        if not isinstance(item, dict):
            issues.append(f"{path} must be an object")
            continue
        _reject_extra_keys(
            item,
            {
                "sheet_name",
                "sheet_state",
                "sheet_position",
                "source_used_range",
                "planned_ranges",
            },
            path,
            issues,
        )
        position = item.get("sheet_position")
        if not isinstance(position, int) or position < 1:
            issues.append(f"{path}.sheet_position must be positive")
        elif position in seen_positions:
            issues.append(f"{path}.sheet_position is duplicated")
        else:
            seen_positions.add(position)
        ranges = item.get("planned_ranges")
        if not _is_string_list(ranges):
            issues.append(f"{path}.planned_ranges must be an array of strings")
        else:
            rectangles: list[Rectangle] = []
            for coordinate_range in ranges:
                try:
                    rectangle = _parse_range(coordinate_range)
                except ValueError:
                    issues.append(f"{path}.planned_ranges contains invalid range")
                    continue
                if any(rectangle.overlaps(existing) for existing in rectangles):
                    issues.append(f"{path}.planned_ranges overlap")
                rectangles.append(rectangle)


def _parse_range(value: str) -> Rectangle:
    if not isinstance(value, str):
        raise ValueError("range must be a string")
    match = _RANGE_RE.fullmatch(value.upper())
    if not match:
        raise ValueError("range is invalid")
    start_column = _column_number(match.group(1))
    start_row = int(match.group(2))
    end_column = _column_number(match.group(3))
    end_row = int(match.group(4))
    if start_row > end_row or start_column > end_column:
        raise ValueError("range start must not exceed range end")
    rectangle = Rectangle(start_row, start_column, end_row, end_column)
    bounds_issue = _bounds_issue(rectangle)
    if bounds_issue:
        raise ValueError(bounds_issue)
    return rectangle


def _bounds_issue(rectangle: Rectangle) -> str | None:
    if rectangle.start_row < 1 or rectangle.end_row > _MAX_ROW:
        return "range_exceeds_excel_row_limit"
    if rectangle.start_column < 1 or rectangle.end_column > _MAX_COLUMN:
        return "range_exceeds_excel_column_limit"
    return None


def _first_collision(
    rectangle: Rectangle,
    occupied: list[Rectangle],
) -> Rectangle | None:
    return next(
        (existing for existing in occupied if rectangle.overlaps(existing)),
        None,
    )


def _column_number(letters: str) -> int:
    value = 0
    for character in letters:
        value = value * 26 + ord(character.upper()) - 64
    return value


def _column_name(column: int) -> str:
    if not 1 <= column <= _MAX_COLUMN:
        raise ValueError("column exceeds Excel limits")
    value = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        value = chr(65 + remainder) + value
    return value


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


def _reject_extra_keys(
    payload: dict[str, Any],
    allowed: set[str],
    path: str,
    issues: list[str],
) -> None:
    extra = sorted(set(payload) - allowed)
    if extra:
        issues.append(f"{path} contains unsupported fields: {', '.join(extra)}")


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in string.hexdigits for character in value)
    )


def _digest(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()
