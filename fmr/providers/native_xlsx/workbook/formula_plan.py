from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from fmr.providers.native_xlsx.workbook.formula_specs import resolve_formula_spec
from fmr.providers.native_xlsx.workbook.semantic import map_workbook_semantics

_MONTH_RE = re.compile(
    r"^(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"[\s\-/']*(?:19|20)?\d{2}(?:\s*(?:a|e|f|actual|estimate|budget|forecast))?$",
    re.IGNORECASE,
)
_TARGET_ROLES = {"income_statement", "budget_forecast"}
_COPY_SPEC = "fmr.formula.forecast_column_copy.v1"
_VALIDATIONS = (
    "fmr.validation.forecast_period_sequence.v1",
    "fmr.validation.formula_consistency.v1",
    "fmr.validation.broken_references.v1",
    "fmr.validation.missing_inputs.v1",
)


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _is_monthly(label: str) -> bool:
    return bool(_MONTH_RE.fullmatch(" ".join(label.strip().split())))


def _target_candidates(semantic_map: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for sheet in semantic_map.get("sheets", []):
        role = sheet.get("role", {}).get("value")
        if role not in _TARGET_ROLES:
            continue
        monthly_periods = [
            period for period in sheet.get("period_columns", [])
            if isinstance(period.get("label"), str) and _is_monthly(period["label"])
        ]
        forecast_periods = [
            period for period in monthly_periods
            if period.get("classification", {}).get("value") == "forecast"
        ]
        if forecast_periods:
            candidates.append({
                "sheet": sheet,
                "monthly_periods": monthly_periods,
                "forecast_periods": forecast_periods,
            })
    return candidates


def plan_monthly_fpa_formula_map(semantic_map: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(semantic_map, dict):
        raise ValueError("semantic map must be an object")
    if semantic_map.get("contract_version") != "workbook-semantic-map.v1":
        raise ValueError("unsupported semantic map contract_version")
    source = semantic_map.get("source")
    if not isinstance(source, dict):
        raise ValueError("semantic map source must be an object")

    for identifier in (_COPY_SPEC, *_VALIDATIONS):
        resolve_formula_spec(identifier)

    semantic_sha256 = _digest(semantic_map)
    candidates = _target_candidates(semantic_map)
    blockers: list[str] = []
    unresolved: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    target_sheet: str | None = None
    periods: list[dict[str, Any]] = []

    if not candidates:
        blockers.append("no_monthly_forecast_target_sheet")
    else:
        candidates.sort(
            key=lambda item: (
                -len(item["forecast_periods"]),
                -len(item["monthly_periods"]),
                item["sheet"]["name"].lower(),
            )
        )
        best = candidates[0]
        if len(candidates) > 1:
            first_key = (len(best["forecast_periods"]), len(best["monthly_periods"]))
            second_key = (len(candidates[1]["forecast_periods"]), len(candidates[1]["monthly_periods"]))
            if first_key == second_key:
                blockers.append("ambiguous_monthly_forecast_target_sheet")
        if not blockers:
            sheet = best["sheet"]
            target_sheet = sheet["name"]
            periods = [
                {
                    "coordinate": period["coordinate"],
                    "column": period["column"],
                    "label": period["label"],
                    "kind": period["classification"]["value"],
                }
                for period in best["monthly_periods"]
            ]
            period_index_by_label = {period["label"]: index for index, period in enumerate(periods)}
            planned_cells: set[str] = set()
            sequence = 0
            for row in sheet.get("metric_rows", []):
                metric = row.get("metric", {}).get("value")
                if not isinstance(metric, str) or metric == "unknown":
                    continue
                row_cells = row.get("period_cells", [])
                by_label = {cell.get("period_label"): cell for cell in row_cells}
                for forecast in best["forecast_periods"]:
                    label = forecast["label"]
                    target = by_label.get(label)
                    if not isinstance(target, dict):
                        unresolved.append({
                            "sheet": target_sheet,
                            "metric": metric,
                            "period_label": label,
                            "target_cell": None,
                            "reason": "forecast_cell_not_mapped",
                        })
                        continue
                    target_cell = target.get("coordinate")
                    if target.get("cell_kind") != "blank":
                        continue
                    index = period_index_by_label.get(label)
                    if index is None or index == 0:
                        unresolved.append({
                            "sheet": target_sheet,
                            "metric": metric,
                            "period_label": label,
                            "target_cell": target_cell,
                            "reason": "no_preceding_period",
                        })
                        continue
                    previous_label = periods[index - 1]["label"]
                    previous = by_label.get(previous_label)
                    if not isinstance(previous, dict):
                        unresolved.append({
                            "sheet": target_sheet,
                            "metric": metric,
                            "period_label": label,
                            "target_cell": target_cell,
                            "reason": "preceding_period_cell_not_mapped",
                        })
                        continue
                    previous_cell = previous.get("coordinate")
                    previous_kind = previous.get("cell_kind")
                    source_type: str | None = None
                    if previous_kind == "formula":
                        source_type = "workbook_formula_cell"
                    elif isinstance(previous_cell, str) and previous_cell in planned_cells:
                        source_type = "planned_formula_cell"
                    if source_type is None:
                        unresolved.append({
                            "sheet": target_sheet,
                            "metric": metric,
                            "period_label": label,
                            "target_cell": target_cell,
                            "reason": "preceding_period_is_not_formula",
                        })
                        continue
                    sequence += 1
                    record_id = f"fmrf_{sequence:06d}"
                    spec = resolve_formula_spec(_COPY_SPEC)
                    records.append({
                        "sequence": sequence,
                        "record_id": record_id,
                        "target": {
                            "sheet": target_sheet,
                            "cell": target_cell,
                            "metric": metric,
                            "period_label": label,
                        },
                        "formula_specification": {
                            "identifier": spec.identifier,
                            "specification_ref": spec.specification_ref,
                            "expression_language": "fmr-expression.v1",
                            "fill_policy": spec.fill_policy,
                        },
                        "bindings": [{
                            "name": "previous_period_formula",
                            "source_type": source_type,
                            "source": {
                                "sheet": target_sheet,
                                "cell": previous_cell,
                                "period_label": previous_label,
                            },
                        }],
                        "validation_checks": list(_VALIDATIONS),
                    })
                    if isinstance(target_cell, str):
                        planned_cells.add(target_cell)

    if unresolved:
        blockers.append("unresolved_forecast_formula_targets")
    if not records:
        blockers.append("no_formula_records_planned")
    blockers = list(dict.fromkeys(blockers))

    provisional = {
        "contract_version": "workbook-formula-plan.v1",
        "plan_type": "monthly_fpa_formula_extension",
        "source": source,
        "semantic_map_sha256": semantic_sha256,
        "target_sheet": target_sheet,
        "periods": periods,
        "records": records,
        "unresolved": unresolved,
        "validation_checks": list(_VALIDATIONS),
        "controls": [
            "dry_run_only",
            "source_workbook_not_modified",
            "existing_nonblank_cells_preserved",
            "semantic_map_evidence_required",
            "declared_formula_specs_only",
            "raw_formula_text_not_emitted",
            "external_links_not_created",
            "ambiguous_targets_fail_closed",
        ],
        "ready_for_write": not blockers,
        "blockers": blockers,
    }
    return {
        **provisional,
        "plan_id": f"fmrfp_{_digest(provisional)[:24]}",
    }


def plan_monthly_fpa_formula_file(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    semantic_map = map_workbook_semantics(source)
    return plan_monthly_fpa_formula_map(semantic_map)


def validate_workbook_formula_plan_payload(
    payload: Any,
    *,
    semantic_map: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("formula plan must be an object",)
    if payload.get("contract_version") != "workbook-formula-plan.v1":
        issues.append("unsupported contract_version")
    if payload.get("plan_type") != "monthly_fpa_formula_extension":
        issues.append("unsupported plan_type")
    if not isinstance(payload.get("plan_id"), str) or not payload.get("plan_id", "").startswith("fmrfp_"):
        issues.append("plan_id is invalid")
    records = payload.get("records")
    if not isinstance(records, list):
        issues.append("records must be an array")
    else:
        expected_sequence = 1
        seen_targets: set[tuple[str, str]] = set()
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                issues.append(f"records[{index}] must be an object")
                continue
            if record.get("sequence") != expected_sequence:
                issues.append(f"records[{index}].sequence is not contiguous")
            expected_sequence += 1
            target = record.get("target")
            if not isinstance(target, dict):
                issues.append(f"records[{index}].target must be an object")
                continue
            key = (target.get("sheet"), target.get("cell"))
            if key in seen_targets:
                issues.append(f"records[{index}] duplicates a target cell")
            seen_targets.add(key)
            specification = record.get("formula_specification")
            if not isinstance(specification, dict) or specification.get("identifier") != _COPY_SPEC:
                issues.append(f"records[{index}] uses an undeclared formula specification")
            bindings = record.get("bindings")
            if not isinstance(bindings, list) or len(bindings) != 1:
                issues.append(f"records[{index}].bindings must contain exactly one dependency")
            elif bindings[0].get("name") != "previous_period_formula":
                issues.append(f"records[{index}] has an invalid dependency binding")
    if payload.get("ready_for_write") and payload.get("blockers"):
        issues.append("ready_for_write cannot be true when blockers are present")
    rendered = json.dumps(payload, sort_keys=True)
    if '"formula":' in rendered or '"value":' in rendered:
        issues.append("formula plan contains forbidden raw formula or value fields")
    if semantic_map is not None:
        expected = plan_monthly_fpa_formula_map(semantic_map)
        if payload != expected:
            issues.append("formula plan does not match deterministic recomputation")
    return tuple(dict.fromkeys(issues))


__all__ = [
    "plan_monthly_fpa_formula_file",
    "plan_monthly_fpa_formula_map",
    "validate_workbook_formula_plan_payload",
]
