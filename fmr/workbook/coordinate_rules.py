from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from fmr.workbook.operation_specs import OPERATION_SPECS


@dataclass(frozen=True)
class WorkbookCoordinateRule:
    source_operation: str
    allocation_kind: str
    rows: int | None
    columns: int | None
    columns_parameter: str | None
    gap_rows: int
    existing_target_mode: str

    @property
    def specification_ref(self) -> str:
        return f"fmr://workbook-coordinate-rules/{self.source_operation}/v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": "workbook-coordinate-rule.v1",
            "specification_ref": self.specification_ref,
            "source_operation": self.source_operation,
            "allocation_kind": self.allocation_kind,
            "footprint": {
                "rows": self.rows,
                "columns": self.columns,
                "columns_parameter": self.columns_parameter,
                "gap_rows": self.gap_rows,
            },
            "existing_target_mode": self.existing_target_mode,
            "controls": [
                "excel_bounds_checked",
                "source_used_range_treated_as_occupied",
                "planned_ranges_must_not_overlap",
                "no_formula_or_value_payloads",
            ],
        }


def _rule(
    source_operation: str,
    allocation_kind: str,
    *,
    rows: int | None = None,
    columns: int | None = None,
    columns_parameter: str | None = None,
    gap_rows: int = 0,
    existing_target_mode: str = "allocate",
) -> WorkbookCoordinateRule:
    return WorkbookCoordinateRule(
        source_operation=source_operation,
        allocation_kind=allocation_kind,
        rows=rows,
        columns=columns,
        columns_parameter=columns_parameter,
        gap_rows=gap_rows,
        existing_target_mode=existing_target_mode,
    )


COORDINATE_RULES: dict[str, WorkbookCoordinateRule] = {
    rule.source_operation: rule
    for rule in (
        _rule("create_assumptions_section", "sheet_block", rows=20, columns=8, existing_target_mode="satisfied"),
        _rule("add_forecast_periods", "column_extension", columns_parameter="forecast_period_count"),
        _rule("create_revenue_schedule", "sheet_block", rows=32, columns=10, existing_target_mode="satisfied"),
        _rule("create_operating_cost_schedule", "sheet_block", rows=32, columns=10, existing_target_mode="satisfied"),
        _rule("create_working_capital_schedule", "sheet_block", rows=32, columns=10, existing_target_mode="satisfied"),
        _rule("create_capital_expenditure_schedule", "sheet_block", rows=32, columns=10, existing_target_mode="satisfied"),
        _rule("create_debt_schedule", "sheet_block", rows=40, columns=10, existing_target_mode="satisfied"),
        _rule("create_interest_schedule", "append_block", rows=18, columns=10, gap_rows=2),
        _rule("create_cash_sweep_schedule", "append_block", rows=18, columns=10, gap_rows=2),
        _rule("create_covenant_schedule", "append_block", rows=18, columns=10, gap_rows=2),
        _rule("create_refinancing_scenarios", "append_block", rows=16, columns=10, gap_rows=2),
        _rule("link_financial_statements", "reference_only"),
        _rule("extend_operating_forecast", "column_extension", columns_parameter="forecast_period_count"),
        _rule("create_free_cash_flow_schedule", "append_block", rows=24, columns=10, gap_rows=2),
        _rule("create_discount_factor_schedule", "append_block", rows=18, columns=10, gap_rows=2),
        _rule("create_terminal_value_section", "append_block", rows=10, columns=8, gap_rows=2),
        _rule("create_enterprise_to_equity_bridge", "append_block", rows=12, columns=8, gap_rows=2),
        _rule("add_valuation_sensitivity", "append_block", rows=12, columns=10, gap_rows=2),
        _rule("add_integrity_checks", "append_block", rows=10, columns=6, gap_rows=2),
        _rule("add_balance_checks", "append_block", rows=8, columns=6, gap_rows=2),
        _rule("add_cash_flow_checks", "append_block", rows=8, columns=6, gap_rows=2),
        _rule("add_liquidity_checks", "append_block", rows=10, columns=6, gap_rows=2),
    )
}


def coordinate_rule_registry_payload() -> dict[str, Any]:
    if set(COORDINATE_RULES) != set(OPERATION_SPECS):
        missing = sorted(set(OPERATION_SPECS) - set(COORDINATE_RULES))
        extra = sorted(set(COORDINATE_RULES) - set(OPERATION_SPECS))
        raise ValueError(f"coordinate rule registry drift: missing={missing}, extra={extra}")
    rules = [COORDINATE_RULES[name].to_dict() for name in sorted(COORDINATE_RULES)]
    provisional = {
        "contract_version": "workbook-coordinate-rule-registry.v1",
        "registry_version": "v1",
        "rules": rules,
    }
    return {**provisional, "registry_sha256": _digest(provisional)}


def _digest(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()
