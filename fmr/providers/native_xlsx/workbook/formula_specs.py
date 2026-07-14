from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from fmr.providers.native_xlsx.workbook.content_specs import CONTENT_SPECS

_ALLOWED_FORMULA_KINDS = {"calculation", "copy_rule", "validation"}
_ALLOWED_DEPENDENCY_SOURCES = {
    "content_slot",
    "period_context",
    "reference_target",
    "source_workbook",
    "validation_context",
}
_ALLOWED_OUTPUT_TYPES = {
    "boolean",
    "currency",
    "decimal",
    "multiple",
    "percentage",
    "preserve_source",
}
_ALLOWED_SIGN_CONVENTIONS = {
    "boolean",
    "neutral",
    "positive_asset",
    "positive_expense",
    "positive_inflow",
    "positive_liability",
}
_ALLOWED_FILL_POLICIES = {
    "across_periods",
    "down_target_range",
    "single_cell",
}
_ALLOWED_DSL_FUNCTIONS = {
    "ADD",
    "AVERAGE",
    "CHANGE",
    "COPY_PREVIOUS_PERIOD",
    "COVENANT_METRIC",
    "DIVIDE",
    "DRIVER_FORECAST",
    "MAX",
    "MUL",
    "NEGATE",
    "POWER",
    "REFINANCING_SOURCES_USES",
    "RUN_VALIDATION",
    "SENSITIVITY_GRID",
    "STRAIGHT_LINE_ROLLFORWARD",
    "SUB",
    "SUM",
    "WORKING_CAPITAL_FROM_DAYS",
}
_TOKEN_RE = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")
_FUNCTION_RE = re.compile(r"\b([A-Z][A-Z0-9_]*)\s*\(")
_A1_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Z]{1,3}[1-9][0-9]*(?![A-Za-z0-9_])")
_GENERATED_FORECAST_RE = re.compile(r"^fmr\.formula\.forecast_column_([1-9][0-9]*)\.v1$")


@dataclass(frozen=True)
class FormulaDependency:
    name: str
    source: str
    identifier: str
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "identifier": self.identifier,
            "required": self.required,
        }


@dataclass(frozen=True)
class WorkbookFormulaSpec:
    identifier: str
    formula_kind: str
    expression_template: str
    dependencies: tuple[FormulaDependency, ...]
    output_type: str
    sign_convention: str
    fill_policy: str
    circularity_policy: str = "forbid"
    identifier_pattern: str | None = None

    @property
    def specification_ref(self) -> str:
        slug = self.identifier.removeprefix("fmr.").removesuffix(".v1").replace(".", "/")
        return f"fmr://workbook-formula-specs/{slug}/v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": "workbook-formula-spec.v1",
            "specification_ref": self.specification_ref,
            "identifier": self.identifier,
            "identifier_pattern": self.identifier_pattern,
            "formula_kind": self.formula_kind,
            "expression_language": "fmr-expression.v1",
            "expression_template": self.expression_template,
            "dependencies": [item.to_dict() for item in self.dependencies],
            "output_type": self.output_type,
            "sign_convention": self.sign_convention,
            "fill_policy": self.fill_policy,
            "circularity_policy": self.circularity_policy,
            "controls": [
                "declared_dependencies_only",
                "external_links_forbidden",
                "raw_cell_coordinates_forbidden",
                "volatile_functions_forbidden",
            ],
        }


def _dependency(name: str, source: str, identifier: str, *, required: bool = True) -> FormulaDependency:
    if source not in _ALLOWED_DEPENDENCY_SOURCES:
        raise ValueError(f"unsupported dependency source: {source}")
    return FormulaDependency(name=name, source=source, identifier=identifier, required=required)


def _input(name: str) -> FormulaDependency:
    return _dependency(name, "content_slot", f"fmr.input.{name}.v1")


def _formula(name: str) -> FormulaDependency:
    return _dependency(name, "content_slot", f"fmr.formula.{name}.v1")


def _source(name: str) -> FormulaDependency:
    return _dependency(name, "source_workbook", f"fmr.source.{name}.v1")


def _period(name: str) -> FormulaDependency:
    return _dependency(name, "period_context", f"fmr.period-context.{name}.v1")


def _spec(
    name: str,
    expression: str,
    dependencies: tuple[FormulaDependency, ...],
    *,
    output_type: str = "currency",
    sign_convention: str = "neutral",
    fill_policy: str = "across_periods",
    formula_kind: str = "calculation",
) -> WorkbookFormulaSpec:
    return WorkbookFormulaSpec(
        identifier=f"fmr.formula.{name}.v1",
        formula_kind=formula_kind,
        expression_template=expression,
        dependencies=dependencies,
        output_type=output_type,
        sign_convention=sign_convention,
        fill_policy=fill_policy,
    )


def _validation(name: str) -> WorkbookFormulaSpec:
    return WorkbookFormulaSpec(
        identifier=f"fmr.validation.{name}.v1",
        formula_kind="validation",
        expression_template="RUN_VALIDATION({{validation_context}})",
        dependencies=(
            _dependency(
                "validation_context",
                "validation_context",
                f"fmr.validation-context.{name}.v1",
            ),
        ),
        output_type="boolean",
        sign_convention="boolean",
        fill_policy="single_cell",
    )


_EXACT_SPECS: tuple[WorkbookFormulaSpec, ...] = (
    _spec(
        "forecast_column_copy",
        "COPY_PREVIOUS_PERIOD({{previous_period_formula}})",
        (_period("previous_period_formula"),),
        output_type="preserve_source",
        formula_kind="copy_rule",
        fill_policy="down_target_range",
    ),
    _spec(
        "revenue_forecast",
        "MUL({{volume_driver}}, {{price_driver}}, ADD(1, {{growth_rate}}))",
        (_input("volume_driver"), _input("price_driver"), _input("growth_rate")),
        sign_convention="positive_inflow",
    ),
    _spec(
        "operating_cost_forecast",
        "ADD({{fixed_cost_driver}}, {{variable_cost_driver}})",
        (_input("fixed_cost_driver"), _input("variable_cost_driver")),
        sign_convention="positive_expense",
    ),
    _spec(
        "net_working_capital",
        "WORKING_CAPITAL_FROM_DAYS({{revenue_base}}, {{cost_base}}, {{receivable_days}}, {{inventory_days}}, {{payable_days}})",
        (
            _source("revenue_base"),
            _source("cost_base"),
            _input("receivable_days"),
            _input("inventory_days"),
            _input("payable_days"),
        ),
        sign_convention="positive_asset",
    ),
    _spec(
        "working_capital_change",
        "CHANGE({{net_working_capital}})",
        (_formula("net_working_capital"),),
    ),
    _spec(
        "capital_expenditure_forecast",
        "DRIVER_FORECAST({{capital_expenditure_driver}})",
        (_input("capital_expenditure_driver"),),
        sign_convention="positive_expense",
    ),
    _spec(
        "depreciation_forecast",
        "STRAIGHT_LINE_ROLLFORWARD({{capital_expenditure_forecast}}, {{useful_life}}, {{opening_net_book_value}})",
        (
            _formula("capital_expenditure_forecast"),
            _input("useful_life"),
            _source("opening_net_book_value"),
        ),
        sign_convention="positive_expense",
    ),
    _spec(
        "closing_debt",
        "MAX(0, SUB({{opening_debt}}, {{scheduled_repayment}}))",
        (_input("opening_debt"), _input("scheduled_repayment")),
        sign_convention="positive_liability",
    ),
    _spec(
        "interest_expense",
        "MUL(AVERAGE({{opening_debt}}, {{closing_debt}}), {{interest_rate}})",
        (_input("opening_debt"), _formula("closing_debt"), _input("interest_rate")),
        sign_convention="positive_expense",
    ),
    _spec(
        "cash_interest",
        "MUL(AVERAGE({{opening_debt}}, {{closing_debt}}), {{interest_rate}})",
        (_input("opening_debt"), _formula("closing_debt"), _input("interest_rate")),
        sign_convention="positive_expense",
    ),
    _spec(
        "cash_sweep",
        "MAX(0, MUL(MAX(0, SUB({{available_cash}}, {{minimum_cash}})), {{sweep_percentage}}))",
        (_source("available_cash"), _input("minimum_cash"), _input("sweep_percentage")),
        sign_convention="positive_expense",
    ),
    _spec(
        "covenant_metric",
        "COVENANT_METRIC({{covenant_inputs}})",
        (_source("covenant_inputs"),),
        output_type="multiple",
    ),
    _spec(
        "covenant_headroom",
        "SUB({{covenant_threshold}}, {{covenant_metric}})",
        (_input("covenant_threshold"), _formula("covenant_metric")),
        output_type="multiple",
    ),
    _spec(
        "refinancing_cash_flow",
        "REFINANCING_SOURCES_USES({{refinancing_amount}}, {{new_interest_rate}}, {{new_maturity}})",
        (_input("refinancing_amount"), _input("new_interest_rate"), _input("new_maturity")),
        sign_convention="positive_inflow",
    ),
    _spec(
        "ebit_after_tax",
        "MUL({{ebit}}, SUB(1, {{tax_rate}}))",
        (_source("ebit"), _source("tax_rate")),
        sign_convention="positive_inflow",
    ),
    _spec(
        "free_cash_flow",
        "ADD({{ebit_after_tax}}, {{depreciation}}, NEGATE({{capital_expenditure}}), NEGATE({{working_capital_change}}))",
        (
            _formula("ebit_after_tax"),
            _source("depreciation"),
            _source("capital_expenditure"),
            _source("working_capital_change"),
        ),
        sign_convention="positive_inflow",
    ),
    _spec(
        "discount_factor",
        "POWER(ADD(1, {{discount_rate}}), NEGATE({{period_index}}))",
        (_input("discount_rate"), _period("period_index")),
        output_type="decimal",
    ),
    _spec(
        "present_value",
        "MUL({{free_cash_flow}}, {{discount_factor}})",
        (_formula("free_cash_flow"), _formula("discount_factor")),
        sign_convention="positive_inflow",
    ),
    _spec(
        "terminal_value",
        "DIVIDE(MUL({{final_period_free_cash_flow}}, ADD(1, {{terminal_growth_rate}})), SUB({{discount_rate}}, {{terminal_growth_rate}}))",
        (
            _source("final_period_free_cash_flow"),
            _input("terminal_growth_rate"),
            _input("discount_rate"),
        ),
        sign_convention="positive_inflow",
    ),
    _spec(
        "enterprise_value",
        "SUM({{present_value}}, {{terminal_value}})",
        (_formula("present_value"), _formula("terminal_value")),
        sign_convention="positive_asset",
    ),
    _spec(
        "net_debt",
        "SUB({{debt}}, {{cash}})",
        (_source("debt"), _source("cash")),
        sign_convention="positive_liability",
    ),
    _spec(
        "equity_value",
        "SUB({{enterprise_value}}, {{net_debt}})",
        (_formula("enterprise_value"), _formula("net_debt")),
        sign_convention="positive_asset",
    ),
    _spec(
        "sensitivity_output",
        "SENSITIVITY_GRID({{sensitivity_axis_one}}, {{sensitivity_axis_two}}, {{equity_value}})",
        (_input("sensitivity_axis_one"), _input("sensitivity_axis_two"), _formula("equity_value")),
        sign_convention="positive_asset",
    ),
    *tuple(
        _validation(name)
        for name in (
            "assumptions_complete",
            "balance_sheet_balance",
            "broken_references",
            "capex_rollforward",
            "cash_flow_reconciliation",
            "cash_sweep_within_available_cash",
            "covenant_headroom",
            "debt_rollforward",
            "debt_service",
            "discount_factors_monotonic",
            "enterprise_equity_bridge",
            "forecast_period_sequence",
            "formula_consistency",
            "free_cash_flow_reconciles",
            "interest_reconciles",
            "minimum_cash",
            "missing_inputs",
            "operating_costs_reconcile",
            "reference_targets_resolved",
            "refinancing_sources_uses",
            "revenue_reconciles",
            "sensitivity_grid_complete",
            "terminal_value_assumptions",
            "working_capital_reconciles",
        )
    ),
)

FORMULA_SPECS: dict[str, WorkbookFormulaSpec] = {item.identifier: item for item in _EXACT_SPECS}
GENERATED_FORECAST_SPEC = WorkbookFormulaSpec(
    identifier="fmr.formula.forecast_column_{period_index}.v1",
    identifier_pattern=r"^fmr\.formula\.forecast_column_([1-9][0-9]*)\.v1$",
    formula_kind="copy_rule",
    expression_template="COPY_PREVIOUS_PERIOD({{previous_period_formula}})",
    dependencies=(_period("previous_period_formula"),),
    output_type="preserve_source",
    sign_convention="neutral",
    fill_policy="down_target_range",
)


def resolve_formula_spec(identifier: str) -> WorkbookFormulaSpec:
    exact = FORMULA_SPECS.get(identifier)
    if exact is not None:
        return exact
    if _GENERATED_FORECAST_RE.fullmatch(identifier):
        return GENERATED_FORECAST_SPEC
    raise KeyError(identifier)


def formula_spec_registry_payload() -> dict[str, Any]:
    _validate_registry()
    specifications = [FORMULA_SPECS[name].to_dict() for name in sorted(FORMULA_SPECS)]
    specifications.append(GENERATED_FORECAST_SPEC.to_dict())
    provisional = {
        "contract_version": "workbook-formula-spec-registry.v1",
        "registry_version": "v1",
        "expression_language": "fmr-expression.v1",
        "specifications": specifications,
    }
    return {**provisional, "registry_sha256": _digest(provisional)}


def _validate_registry() -> None:
    required = {
        slot.identifier
        for spec in CONTENT_SPECS.values()
        for slot in spec.slots
        if slot.content_kind in {"formula_identifier", "validation_identifier"}
        and slot.identifier is not None
    }
    missing = sorted(required - set(FORMULA_SPECS))
    if missing:
        raise ValueError(f"formula spec registry missing content identifiers: {missing}")
    if len(FORMULA_SPECS) != len(_EXACT_SPECS):
        raise ValueError("formula spec registry contains duplicate identifiers")
    for spec in (*_EXACT_SPECS, GENERATED_FORECAST_SPEC):
        _validate_spec(spec)
    _validate_dependency_graph()


def _validate_spec(spec: WorkbookFormulaSpec) -> None:
    if spec.formula_kind not in _ALLOWED_FORMULA_KINDS:
        raise ValueError(f"unsupported formula kind: {spec.formula_kind}")
    if spec.output_type not in _ALLOWED_OUTPUT_TYPES:
        raise ValueError(f"unsupported formula output type: {spec.output_type}")
    if spec.sign_convention not in _ALLOWED_SIGN_CONVENTIONS:
        raise ValueError(f"unsupported sign convention: {spec.sign_convention}")
    if spec.fill_policy not in _ALLOWED_FILL_POLICIES:
        raise ValueError(f"unsupported fill policy: {spec.fill_policy}")
    if spec.circularity_policy != "forbid":
        raise ValueError("only forbidden circularity is supported")
    if any(character in spec.expression_template for character in "!$[]"):
        raise ValueError(f"formula spec contains workbook-specific reference syntax: {spec.identifier}")
    if _A1_RE.search(spec.expression_template):
        raise ValueError(f"formula spec contains raw cell coordinates: {spec.identifier}")
    tokens = set(_TOKEN_RE.findall(spec.expression_template))
    dependency_names = {item.name for item in spec.dependencies}
    if tokens != dependency_names:
        raise ValueError(
            f"formula dependency mismatch for {spec.identifier}: tokens={sorted(tokens)} dependencies={sorted(dependency_names)}"
        )
    if len(dependency_names) != len(spec.dependencies):
        raise ValueError(f"formula spec contains duplicate dependency names: {spec.identifier}")
    functions = set(_FUNCTION_RE.findall(spec.expression_template))
    unsupported = sorted(functions - _ALLOWED_DSL_FUNCTIONS)
    if unsupported:
        raise ValueError(f"unsupported FMR expression functions for {spec.identifier}: {unsupported}")


def _validate_dependency_graph() -> None:
    graph: dict[str, set[str]] = {identifier: set() for identifier in FORMULA_SPECS}
    for identifier, spec in FORMULA_SPECS.items():
        for dependency in spec.dependencies:
            if dependency.source == "content_slot" and dependency.identifier in FORMULA_SPECS:
                graph[identifier].add(dependency.identifier)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError(f"formula dependency cycle detected at {node}")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def _digest(payload: Any) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()
