from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkbookOperationSpec:
    source_operation: str
    action: str
    semantic_role: str
    target_scope: str
    cardinality: str
    accepted_sheet_roles: tuple[str, ...]
    required_sheet_roles: tuple[str, ...]
    name_aliases: tuple[str, ...]
    metric_hints: tuple[str, ...]
    canonical_sheet_name: str | None
    placement: str
    create_if_missing: bool

    @property
    def specification_ref(self) -> str:
        return f"fmr://workbook-operations/{self.source_operation}/v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": "workbook-operation-spec.v1",
            "specification_ref": self.specification_ref,
            "source_operation": self.source_operation,
            "action": self.action,
            "semantic_role": self.semantic_role,
            "target_policy": {
                "scope": self.target_scope,
                "cardinality": self.cardinality,
                "accepted_sheet_roles": list(self.accepted_sheet_roles),
                "required_sheet_roles": list(self.required_sheet_roles),
                "name_aliases": list(self.name_aliases),
                "metric_hints": list(self.metric_hints),
                "canonical_sheet_name": self.canonical_sheet_name,
                "placement": self.placement,
                "create_if_missing": self.create_if_missing,
            },
            "conflict_policy": "reuse_unique_match_or_fail",
            "postconditions": [
                "target_resolution_is_deterministic",
                "existing_workbook_content_is_preserved",
                "no_cell_or_formula_instructions_are_emitted",
            ],
        }


def _spec(
    source_operation: str,
    action: str,
    semantic_role: str,
    *,
    scope: str = "sheet",
    cardinality: str = "one_or_create",
    roles: tuple[str, ...] = (),
    required_roles: tuple[str, ...] = (),
    aliases: tuple[str, ...] = (),
    metrics: tuple[str, ...] = (),
    canonical: str | None = None,
    placement: str = "after_last_visible_sheet",
    create: bool = True,
) -> WorkbookOperationSpec:
    return WorkbookOperationSpec(
        source_operation=source_operation,
        action=action,
        semantic_role=semantic_role,
        target_scope=scope,
        cardinality=cardinality,
        accepted_sheet_roles=roles,
        required_sheet_roles=required_roles,
        name_aliases=aliases,
        metric_hints=metrics,
        canonical_sheet_name=canonical,
        placement=placement,
        create_if_missing=create,
    )


OPERATION_SPECS: dict[str, WorkbookOperationSpec] = {
    spec.source_operation: spec
    for spec in (
        _spec(
            "create_assumptions_section",
            "ensure_sheet",
            "assumptions",
            roles=("assumptions",),
            aliases=("assumptions", "drivers", "inputs"),
            canonical="Assumptions",
        ),
        _spec(
            "add_forecast_periods",
            "append_periods",
            "forecast_periods",
            scope="sheet_set",
            cardinality="many",
            roles=(
                "income_statement",
                "balance_sheet",
                "cash_flow_statement",
                "debt_schedule",
            ),
            placement="append_right_of_used_range",
            create=False,
        ),
        _spec(
            "create_revenue_schedule",
            "ensure_sheet",
            "revenue_schedule",
            aliases=("revenue schedule", "revenue build", "sales forecast"),
            metrics=("revenue",),
            canonical="Revenue Schedule",
        ),
        _spec(
            "create_operating_cost_schedule",
            "ensure_sheet",
            "operating_cost_schedule",
            aliases=(
                "operating cost schedule",
                "operating costs",
                "opex schedule",
            ),
            canonical="Operating Cost Schedule",
        ),
        _spec(
            "create_working_capital_schedule",
            "ensure_sheet",
            "working_capital_schedule",
            aliases=(
                "working capital schedule",
                "working capital",
                "wc schedule",
            ),
            canonical="Working Capital",
        ),
        _spec(
            "create_capital_expenditure_schedule",
            "ensure_sheet",
            "capital_expenditure_schedule",
            aliases=(
                "capital expenditure schedule",
                "capital expenditure",
                "capex schedule",
                "capex",
            ),
            metrics=("capital_expenditure",),
            canonical="Capital Expenditure",
        ),
        _spec(
            "create_debt_schedule",
            "ensure_sheet",
            "debt_schedule",
            roles=("debt_schedule",),
            aliases=("debt schedule", "borrowings", "loans"),
            canonical="Debt Schedule",
        ),
        _spec(
            "create_interest_schedule",
            "ensure_sheet",
            "interest_schedule",
            scope="section",
            roles=("debt_schedule",),
            aliases=("interest schedule", "debt schedule"),
            canonical="Debt Schedule",
            placement="append_below_used_range",
        ),
        _spec(
            "create_cash_sweep_schedule",
            "ensure_sheet",
            "cash_sweep_schedule",
            scope="section",
            roles=("debt_schedule",),
            aliases=("cash sweep", "debt schedule"),
            canonical="Debt Schedule",
            placement="append_below_used_range",
        ),
        _spec(
            "create_covenant_schedule",
            "ensure_sheet",
            "covenant_schedule",
            scope="section",
            roles=("debt_schedule",),
            aliases=("covenant schedule", "covenants", "debt schedule"),
            canonical="Debt Schedule",
            placement="append_below_used_range",
        ),
        _spec(
            "create_refinancing_scenarios",
            "add_scenario",
            "refinancing",
            scope="section",
            roles=("debt_schedule",),
            aliases=("refinancing", "debt schedule"),
            canonical="Refinancing",
            placement="append_below_used_range",
        ),
        _spec(
            "link_financial_statements",
            "link_components",
            "financial_statements",
            scope="sheet_set",
            cardinality="required_roles",
            required_roles=(
                "income_statement",
                "balance_sheet",
                "cash_flow_statement",
            ),
            placement="link_existing_sheets",
            create=False,
        ),
        _spec(
            "extend_operating_forecast",
            "append_periods",
            "operating_forecast",
            scope="sheet_set",
            cardinality="many",
            roles=(
                "income_statement",
                "balance_sheet",
                "cash_flow_statement",
            ),
            placement="append_right_of_used_range",
            create=False,
        ),
        _spec(
            "create_free_cash_flow_schedule",
            "ensure_sheet",
            "free_cash_flow_schedule",
            scope="section",
            roles=("valuation",),
            aliases=("free cash flow", "dcf", "valuation"),
            metrics=("free_cash_flow",),
            canonical="Valuation",
            placement="append_below_used_range",
        ),
        _spec(
            "create_discount_factor_schedule",
            "ensure_sheet",
            "discount_factor_schedule",
            scope="section",
            roles=("valuation",),
            aliases=("discount factor", "dcf", "valuation"),
            metrics=("wacc",),
            canonical="Valuation",
            placement="append_below_used_range",
        ),
        _spec(
            "create_terminal_value_section",
            "ensure_section",
            "terminal_value",
            scope="section",
            roles=("valuation",),
            aliases=("terminal value", "dcf", "valuation"),
            metrics=("terminal_value",),
            canonical="Valuation",
            placement="append_below_used_range",
        ),
        _spec(
            "create_enterprise_to_equity_bridge",
            "ensure_section",
            "enterprise_to_equity_bridge",
            scope="section",
            roles=("valuation",),
            aliases=(
                "enterprise to equity bridge",
                "equity bridge",
                "valuation",
            ),
            canonical="Valuation",
            placement="append_below_used_range",
        ),
        _spec(
            "add_valuation_sensitivity",
            "add_sensitivity",
            "valuation",
            scope="section",
            roles=("valuation",),
            aliases=("valuation", "dcf", "sensitivity"),
            canonical="Valuation",
            placement="append_below_used_range",
        ),
        _spec(
            "add_integrity_checks",
            "add_control",
            "integrity",
            scope="section",
            aliases=("model checks", "checks", "controls"),
            canonical="Model Checks",
            placement="append_below_used_range",
        ),
        _spec(
            "add_balance_checks",
            "add_control",
            "balance",
            scope="section",
            roles=("balance_sheet",),
            aliases=("balance checks", "model checks", "checks"),
            canonical="Model Checks",
            placement="append_below_used_range",
        ),
        _spec(
            "add_cash_flow_checks",
            "add_control",
            "cash_flow",
            scope="section",
            roles=("cash_flow_statement",),
            aliases=("cash flow checks", "model checks", "checks"),
            canonical="Model Checks",
            placement="append_below_used_range",
        ),
        _spec(
            "add_liquidity_checks",
            "add_control",
            "liquidity",
            scope="section",
            roles=("debt_schedule",),
            aliases=("liquidity checks", "model checks", "checks"),
            canonical="Liquidity Checks",
            placement="append_below_used_range",
        ),
    )
}


def operation_spec_registry_payload() -> dict[str, Any]:
    specifications = [
        OPERATION_SPECS[name].to_dict()
        for name in sorted(OPERATION_SPECS)
    ]
    provisional = {
        "contract_version": "workbook-operation-spec-registry.v1",
        "registry_version": "v1",
        "specifications": specifications,
    }
    return {
        **provisional,
        "registry_sha256": _digest(provisional),
    }


def _digest(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()
