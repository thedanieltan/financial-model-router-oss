from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from fmr.providers.native_xlsx.workbook.coordinate_rules import COORDINATE_RULES


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


@dataclass(frozen=True)
class ContentSlotSpec:
    slot_id: str
    row_offset: int
    column_offset: int
    row_span: int
    column_span: int
    content_kind: str
    label: str | None
    identifier: str | None
    format_role: str
    editable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "relative_position": {
                "row_offset": self.row_offset,
                "column_offset": self.column_offset,
                "row_span": self.row_span,
                "column_span": self.column_span,
            },
            "content_kind": self.content_kind,
            "label": self.label,
            "identifier": self.identifier,
            "format_role": self.format_role,
            "editable": self.editable,
        }


@dataclass(frozen=True)
class WorkbookContentSpec:
    source_operation: str
    template_kind: str
    title: str
    slots: tuple[ContentSlotSpec, ...]
    validation_ids: tuple[str, ...]

    @property
    def specification_ref(self) -> str:
        return f"fmr://workbook-content-specs/{self.source_operation}/v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": "workbook-content-spec.v1",
            "specification_ref": self.specification_ref,
            "source_operation": self.source_operation,
            "template_kind": self.template_kind,
            "title": self.title,
            "slots": [slot.to_dict() for slot in self.slots],
            "validation_ids": list(self.validation_ids),
            "controls": [
                "identifiers_are_symbolic",
                "labels_are_fmr_owned",
                "no_formula_expressions",
                "no_input_values",
                "no_number_formats_or_colours",
            ],
        }


def _slot(
    slot_id: str,
    row: int,
    column: int,
    kind: str,
    *,
    label: str | None = None,
    identifier: str | None = None,
    format_role: str,
    editable: bool = False,
    row_span: int = 1,
    column_span: int = 1,
) -> ContentSlotSpec:
    if kind not in _ALLOWED_KINDS:
        raise ValueError(f"unsupported content kind: {kind}")
    if format_role not in _ALLOWED_FORMAT_ROLES:
        raise ValueError(f"unsupported format role: {format_role}")
    if row < 0 or column < 0 or row_span < 1 or column_span < 1:
        raise ValueError("content slot coordinates must be non-negative with positive spans")
    if kind == "label" and not label:
        raise ValueError("label slots require label text")
    if kind != "label" and not identifier:
        raise ValueError(f"{kind} slots require an identifier")
    return ContentSlotSpec(
        slot_id=slot_id,
        row_offset=row,
        column_offset=column,
        row_span=row_span,
        column_span=column_span,
        content_kind=kind,
        label=label,
        identifier=identifier,
        format_role=format_role,
        editable=editable,
    )


def _schedule(
    source_operation: str,
    title: str,
    *,
    inputs: tuple[tuple[str, str], ...] = (),
    outputs: tuple[tuple[str, str], ...] = (),
    validations: tuple[str, ...] = (),
) -> WorkbookContentSpec:
    rule = COORDINATE_RULES[source_operation]
    width = rule.columns or 8
    slots: list[ContentSlotSpec] = [
        _slot("title", 0, 0, "label", label=title, format_role="section_title", column_span=width),
        _slot("line_item_header", 1, 0, "label", label="Line item", format_role="header"),
        _slot(
            "period_header",
            1,
            1,
            "period_header",
            identifier="fmr.period.series.v1",
            format_role="period",
            column_span=max(1, width - 1),
        ),
    ]
    row = 2
    for slot_id, label in inputs:
        slots.append(_slot(f"{slot_id}_label", row, 0, "label", label=label, format_role="label"))
        slots.append(
            _slot(
                slot_id,
                row,
                1,
                "input_placeholder",
                identifier=f"fmr.input.{slot_id}.v1",
                format_role="input",
                editable=True,
                column_span=max(1, width - 1),
            )
        )
        row += 1
    for slot_id, label in outputs:
        slots.append(_slot(f"{slot_id}_label", row, 0, "label", label=label, format_role="label"))
        slots.append(
            _slot(
                slot_id,
                row,
                1,
                "formula_identifier",
                identifier=f"fmr.formula.{slot_id}.v1",
                format_role="output",
                column_span=max(1, width - 1),
            )
        )
        row += 1
    for index, validation_id in enumerate(validations):
        slots.append(
            _slot(
                f"validation_{index + 1}",
                row + index,
                0,
                "validation_identifier",
                identifier=validation_id,
                format_role="control",
                column_span=width,
            )
        )
    return WorkbookContentSpec(
        source_operation=source_operation,
        template_kind="schedule",
        title=title,
        slots=tuple(slots),
        validation_ids=validations,
    )


def _control(source_operation: str, title: str, checks: tuple[tuple[str, str], ...]) -> WorkbookContentSpec:
    rule = COORDINATE_RULES[source_operation]
    width = rule.columns or 6
    slots = [
        _slot("title", 0, 0, "label", label=title, format_role="section_title", column_span=width)
    ]
    for index, (check_id, label) in enumerate(checks, start=1):
        slots.extend(
            (
                _slot(
                    f"{check_id}_label",
                    index,
                    0,
                    "label",
                    label=label,
                    format_role="label",
                    column_span=max(1, width - 2),
                ),
                _slot(
                    check_id,
                    index,
                    max(1, width - 2),
                    "validation_identifier",
                    identifier=f"fmr.validation.{check_id}.v1",
                    format_role="control",
                    column_span=2,
                ),
            )
        )
    return WorkbookContentSpec(
        source_operation=source_operation,
        template_kind="control_block",
        title=title,
        slots=tuple(slots),
        validation_ids=tuple(f"fmr.validation.{check_id}.v1" for check_id, _ in checks),
    )


def _period_extension(source_operation: str, title: str) -> WorkbookContentSpec:
    return WorkbookContentSpec(
        source_operation=source_operation,
        template_kind="period_extension",
        title=title,
        slots=(
            _slot(
                "period_column",
                0,
                0,
                "period_header",
                identifier="fmr.period.forecast_column.v1",
                format_role="period",
            ),
            _slot(
                "forecast_copy_rule",
                1,
                0,
                "formula_identifier",
                identifier="fmr.formula.forecast_column_copy.v1",
                format_role="output",
            ),
        ),
        validation_ids=("fmr.validation.forecast_period_sequence.v1",),
    )


def _reference(source_operation: str, title: str, refs: tuple[str, ...]) -> WorkbookContentSpec:
    return WorkbookContentSpec(
        source_operation=source_operation,
        template_kind="reference_only",
        title=title,
        slots=tuple(
            _slot(
                f"reference_{index}",
                0,
                0,
                "reference_identifier",
                identifier=ref,
                format_role="reference",
            )
            for index, ref in enumerate(refs, start=1)
        ),
        validation_ids=("fmr.validation.reference_targets_resolved.v1",),
    )


CONTENT_SPECS: dict[str, WorkbookContentSpec] = {
    spec.source_operation: spec
    for spec in (
        _schedule(
            "create_assumptions_section",
            "Model assumptions",
            inputs=(("forecast_horizon", "Forecast horizon"), ("scenario", "Scenario"), ("currency", "Currency")),
            validations=("fmr.validation.assumptions_complete.v1",),
        ),
        _period_extension("add_forecast_periods", "Forecast periods"),
        _schedule(
            "create_revenue_schedule",
            "Revenue schedule",
            inputs=(("volume_driver", "Volume driver"), ("price_driver", "Price driver"), ("growth_rate", "Growth rate")),
            outputs=(("revenue_forecast", "Revenue"),),
            validations=("fmr.validation.revenue_reconciles.v1",),
        ),
        _schedule(
            "create_operating_cost_schedule",
            "Operating cost schedule",
            inputs=(("fixed_cost_driver", "Fixed cost driver"), ("variable_cost_driver", "Variable cost driver")),
            outputs=(("operating_cost_forecast", "Operating costs"),),
            validations=("fmr.validation.operating_costs_reconcile.v1",),
        ),
        _schedule(
            "create_working_capital_schedule",
            "Working capital schedule",
            inputs=(("receivable_days", "Receivable days"), ("inventory_days", "Inventory days"), ("payable_days", "Payable days")),
            outputs=(("net_working_capital", "Net working capital"), ("working_capital_change", "Change in working capital")),
            validations=("fmr.validation.working_capital_reconciles.v1",),
        ),
        _schedule(
            "create_capital_expenditure_schedule",
            "Capital expenditure schedule",
            inputs=(("capital_expenditure_driver", "Capital expenditure driver"), ("useful_life", "Useful life")),
            outputs=(("capital_expenditure_forecast", "Capital expenditure"), ("depreciation_forecast", "Depreciation")),
            validations=("fmr.validation.capex_rollforward.v1",),
        ),
        _schedule(
            "create_debt_schedule",
            "Debt schedule",
            inputs=(("opening_debt", "Opening debt"), ("interest_rate", "Interest rate"), ("scheduled_repayment", "Scheduled repayment")),
            outputs=(("closing_debt", "Closing debt"), ("interest_expense", "Interest expense")),
            validations=("fmr.validation.debt_rollforward.v1",),
        ),
        _schedule(
            "create_interest_schedule",
            "Interest schedule",
            inputs=(("interest_rate", "Interest rate"),),
            outputs=(("cash_interest", "Cash interest"),),
            validations=("fmr.validation.interest_reconciles.v1",),
        ),
        _schedule(
            "create_cash_sweep_schedule",
            "Cash sweep schedule",
            inputs=(("minimum_cash", "Minimum cash"), ("sweep_percentage", "Sweep percentage")),
            outputs=(("cash_sweep", "Cash sweep"),),
            validations=("fmr.validation.cash_sweep_within_available_cash.v1",),
        ),
        _schedule(
            "create_covenant_schedule",
            "Covenant schedule",
            inputs=(("covenant_threshold", "Covenant threshold"),),
            outputs=(("covenant_metric", "Covenant metric"), ("covenant_headroom", "Headroom")),
            validations=("fmr.validation.covenant_headroom.v1",),
        ),
        _schedule(
            "create_refinancing_scenarios",
            "Refinancing scenarios",
            inputs=(("refinancing_amount", "Refinancing amount"), ("new_interest_rate", "New interest rate"), ("new_maturity", "New maturity")),
            outputs=(("refinancing_cash_flow", "Refinancing cash flow"),),
            validations=("fmr.validation.refinancing_sources_uses.v1",),
        ),
        _reference(
            "link_financial_statements",
            "Financial statement links",
            ("fmr.reference.income_statement.v1", "fmr.reference.balance_sheet.v1", "fmr.reference.cash_flow_statement.v1"),
        ),
        _period_extension("extend_operating_forecast", "Operating forecast extension"),
        _schedule(
            "create_free_cash_flow_schedule",
            "Free cash flow schedule",
            outputs=(("ebit_after_tax", "EBIT after tax"), ("free_cash_flow", "Free cash flow")),
            validations=("fmr.validation.free_cash_flow_reconciles.v1",),
        ),
        _schedule(
            "create_discount_factor_schedule",
            "Discount factor schedule",
            inputs=(("discount_rate", "Discount rate"),),
            outputs=(("discount_factor", "Discount factor"), ("present_value", "Present value")),
            validations=("fmr.validation.discount_factors_monotonic.v1",),
        ),
        _schedule(
            "create_terminal_value_section",
            "Terminal value",
            inputs=(("terminal_growth_rate", "Terminal growth rate"),),
            outputs=(("terminal_value", "Terminal value"),),
            validations=("fmr.validation.terminal_value_assumptions.v1",),
        ),
        _schedule(
            "create_enterprise_to_equity_bridge",
            "Enterprise to equity bridge",
            outputs=(("enterprise_value", "Enterprise value"), ("net_debt", "Net debt"), ("equity_value", "Equity value")),
            validations=("fmr.validation.enterprise_equity_bridge.v1",),
        ),
        _schedule(
            "add_valuation_sensitivity",
            "Valuation sensitivity",
            inputs=(("sensitivity_axis_one", "Sensitivity axis 1"), ("sensitivity_axis_two", "Sensitivity axis 2")),
            outputs=(("sensitivity_output", "Valuation output"),),
            validations=("fmr.validation.sensitivity_grid_complete.v1",),
        ),
        _control(
            "add_integrity_checks",
            "Model integrity checks",
            (("formula_consistency", "Formula consistency"), ("missing_inputs", "Missing inputs"), ("broken_references", "Broken references")),
        ),
        _control("add_balance_checks", "Balance sheet checks", (("balance_sheet_balance", "Assets equal liabilities and equity"),)),
        _control("add_cash_flow_checks", "Cash flow checks", (("cash_flow_reconciliation", "Cash flow reconciles to cash movement"),)),
        _control(
            "add_liquidity_checks",
            "Liquidity checks",
            (("minimum_cash", "Minimum cash maintained"), ("debt_service", "Debt service capacity")),
        ),
    )
}


def content_spec_registry_payload() -> dict[str, Any]:
    if set(CONTENT_SPECS) != set(COORDINATE_RULES):
        missing = sorted(set(COORDINATE_RULES) - set(CONTENT_SPECS))
        extra = sorted(set(CONTENT_SPECS) - set(COORDINATE_RULES))
        raise ValueError(f"content spec registry drift: missing={missing}, extra={extra}")
    specs = [CONTENT_SPECS[name].to_dict() for name in sorted(CONTENT_SPECS)]
    provisional = {
        "contract_version": "workbook-content-spec-registry.v1",
        "registry_version": "v1",
        "specifications": specs,
    }
    return {**provisional, "registry_sha256": _digest(provisional)}


def _digest(payload: Any) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()
