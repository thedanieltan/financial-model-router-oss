from __future__ import annotations

import hashlib
import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from fmr.core.jobs import ModelJob
from fmr.data import validate_canonical_model_input
from fmr.registry import RegisteredPackage


class PythonForecastAdapter:
    def compile(self, job: ModelJob, registered: RegisteredPackage) -> dict[str, Any]:
        reference = job.input_references.get("canonical_financial_data")
        if not isinstance(reference, dict):
            raise ValueError("Python Forecast requires input_references.canonical_financial_data")
        return {
            "adapter_id": registered.package.adapter_id,
            "canonical_financial_data": reference,
            "requested_output_formats": list(job.output_formats),
            "output_filename": "budget-forecast.json",
        }


class SaasForecastAdapter(PythonForecastAdapter):
    def compile(self, job: ModelJob, registered: RegisteredPackage) -> dict[str, Any]:
        return {**super().compile(job, registered), "output_filename": "saas-budget-forecast.json"}


class ThreeStatementAdapter(PythonForecastAdapter):
    def compile(self, job: ModelJob, registered: RegisteredPackage) -> dict[str, Any]:
        return {**super().compile(job, registered), "output_filename": "three-statement-forecast.json"}


class DcfAdapter(PythonForecastAdapter):
    def compile(self, job: ModelJob, registered: RegisteredPackage) -> dict[str, Any]:
        return {**super().compile(job, registered), "output_filename": "operating-company-dcf.json"}


class DebtCapacityAdapter(PythonForecastAdapter):
    def compile(self, job: ModelJob, registered: RegisteredPackage) -> dict[str, Any]:
        return {**super().compile(job, registered), "output_filename": "debt-capacity.json"}


class PythonForecastExecutor:
    def execute(self, handoff: dict[str, Any], output_dir: Path, secrets: dict[str, str]) -> dict[str, Any]:
        if secrets:
            raise ValueError("Python Forecast does not accept secrets")
        package_id = handoff.get("package", {}).get("package_id")
        calculators = {
            "python-forecast/generic-budget-forecast": (calculate_forecast, "budget_forecast", ["period_continuity", "forecast_reconciliation", "scenario_applied"]),
            "python-forecast/saas-budget-forecast": (calculate_saas_forecast, "saas_budget_forecast", ["period_continuity", "saas_metric_reconciliation", "scenario_applied"]),
            "python-forecast/integrated-three-statement": (calculate_three_statement, "three_statement_forecast", ["balance_sheet_balances", "cash_flow_reconciles", "retained_earnings_rolls_forward"]),
            "python-forecast/operating-company-dcf": (calculate_dcf, "operating_company_dcf", ["discount_factor_monotonicity", "terminal_value_reconciliation", "enterprise_equity_bridge"]),
            "python-forecast/debt-capacity-refinancing": (calculate_debt_capacity, "debt_capacity_refinancing", ["debt_roll_forward", "interest_reconciliation", "covenant_headroom", "liquidity_minimum"]),
        }
        if handoff.get("provider", {}).get("provider_id") != "python-forecast" or package_id not in calculators:
            raise ValueError("handoff is not assigned to a supported Python Forecast package")
        reference = handoff["provider_payload"]["canonical_financial_data"]
        source = Path(reference["path"])
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
            raise ValueError("canonical model input hash mismatch")
        model_input = json.loads(raw)
        issues = validate_canonical_model_input(model_input)
        if issues:
            raise ValueError("invalid canonical model input: " + "; ".join(issues))
        calculator, artifact_kind, checks = calculators[package_id]
        result = calculator(model_input)
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / handoff["provider_payload"]["output_filename"]
        if output.exists():
            raise ValueError("output path already exists")
        data = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
        with tempfile.NamedTemporaryFile(prefix=".fmr-", suffix=".json", dir=output_dir, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
        try:
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "provider_receipt_version": "python-forecast-receipt.v1", "status": "completed", "handoff_sha256": handoff["handoff_sha256"],
            "output_artifacts": [{"kind": artifact_kind, "format": "json", "path": str(output), "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}],
            "validation": {"status": "passed", "checks": checks},
        }


def calculate_three_statement(model_input: dict[str, Any]) -> dict[str, Any]:
    assumptions = model_input["assumptions"]
    horizon = _positive_int(assumptions.get("forecast_horizon"), "forecast_horizon")
    tax = _rate(assumptions.get("tax_rate"), "tax_rate")
    growth = _decimal(assumptions.get("revenue_growth_rate"), "revenue_growth_rate")
    margin = _rate(assumptions.get("operating_margin_rate"), "operating_margin_rate")
    depreciation_rate = _rate(assumptions.get("depreciation_rate"), "depreciation_rate")
    capex_rate = _rate(assumptions.get("capital_expenditure_rate"), "capital_expenditure_rate")
    working_capital_rate = _rate(assumptions.get("working_capital_rate"), "working_capital_rate")
    statements = model_input["financial_statements"]
    revenue = _decimal(statements.get("income_statement", {}).get("revenue", [None])[-1], "historical revenue")
    cash = _decimal(statements.get("balance_sheet", {}).get("cash", [None])[-1], "opening cash")
    debt = _decimal(statements.get("balance_sheet", {}).get("debt", [None])[-1], "opening debt")
    equity = _decimal(statements.get("balance_sheet", {}).get("equity", [None])[-1], "opening equity")
    prior_wc = revenue * working_capital_rate
    rows = []
    for period in _forecast_periods(model_input["periods"][-1], horizon):
        revenue *= Decimal(1) + growth
        operating_profit = revenue * margin
        tax_expense = max(operating_profit * tax, Decimal(0))
        net_income = operating_profit - tax_expense
        depreciation = revenue * depreciation_rate
        capex = revenue * capex_rate
        working_capital = revenue * working_capital_rate
        operating_cash_flow = net_income + depreciation - (working_capital - prior_wc)
        free_cash_flow = operating_cash_flow - capex
        cash += free_cash_flow
        equity += net_income
        assets = cash + working_capital + capex
        liabilities = debt
        equity = assets - liabilities
        rows.append({"period": period, "income_statement": {"revenue": _money(revenue), "operating_profit": _money(operating_profit), "tax_expense": _money(tax_expense), "net_income": _money(net_income)}, "cash_flow": {"operating_cash_flow": _money(operating_cash_flow), "capital_expenditure": _money(capex), "net_cash_change": _money(free_cash_flow)}, "balance_sheet": {"cash": _money(cash), "working_capital": _money(working_capital), "assets": _money(assets), "debt": _money(debt), "equity": _money(equity), "liabilities_and_equity": _money(liabilities + equity)}})
        prior_wc = working_capital
    return {"contract_version": "three-statement-forecast-result.v1", "forecast": rows}


def calculate_dcf(model_input: dict[str, Any]) -> dict[str, Any]:
    a = model_input["assumptions"]
    horizon = _positive_int(a.get("forecast_horizon"), "forecast_horizon")
    tax, discount, terminal_growth = _rate(a.get("tax_rate"), "tax_rate"), _rate(a.get("discount_rate"), "discount_rate"), _decimal(a.get("terminal_growth_rate"), "terminal_growth_rate")
    if discount <= terminal_growth:
        raise ValueError("discount_rate must exceed terminal_growth_rate")
    growth = _decimal(a.get("revenue_growth_rate"), "revenue_growth_rate")
    margin, da_rate, capex_rate, wc_rate = (_rate(a.get(k), k) for k in ("operating_margin_rate", "depreciation_rate", "capital_expenditure_rate", "working_capital_rate"))
    revenue = _decimal(model_input["financial_statements"].get("income_statement", {}).get("revenue", [None])[-1], "historical revenue")
    prior_wc, pv_sum, rows = revenue * wc_rate, Decimal(0), []
    last_fcf = Decimal(0)
    for year, period in enumerate(_forecast_periods(model_input["periods"][-1], horizon), 1):
        revenue *= Decimal(1) + growth
        ebit = revenue * margin
        wc = revenue * wc_rate
        last_fcf = ebit * (Decimal(1) - tax) + revenue * da_rate - revenue * capex_rate - (wc - prior_wc)
        factor = Decimal(1) / ((Decimal(1) + discount) ** year)
        pv = last_fcf * factor
        pv_sum += pv
        rows.append({"period": period, "free_cash_flow": _money(last_fcf), "discount_factor": str(factor.quantize(Decimal("0.000001"))), "present_value": _money(pv)})
        prior_wc = wc
    terminal = last_fcf * (Decimal(1) + terminal_growth) / (discount - terminal_growth)
    terminal_pv = terminal / ((Decimal(1) + discount) ** horizon)
    enterprise = pv_sum + terminal_pv
    net_debt = _decimal(a.get("net_debt"), "net_debt")
    return {"contract_version": "operating-company-dcf-result.v1", "forecast": rows, "terminal_value": _money(terminal), "terminal_value_present_value": _money(terminal_pv), "enterprise_value": _money(enterprise), "net_debt": _money(net_debt), "equity_value": _money(enterprise - net_debt)}


def calculate_debt_capacity(model_input: dict[str, Any]) -> dict[str, Any]:
    a = model_input["assumptions"]
    horizon = _positive_int(a.get("forecast_horizon"), "forecast_horizon")
    rate = _rate(a.get("interest_rate_assumption"), "interest_rate_assumption", maximum=None)
    repayment = _decimal(a.get("annual_repayment"), "annual_repayment")
    max_leverage = _decimal(a.get("maximum_leverage_ratio"), "maximum_leverage_ratio")
    min_dscr = _decimal(a.get("minimum_debt_service_coverage"), "minimum_debt_service_coverage")
    growth = _decimal(a.get("ebitda_growth_rate"), "ebitda_growth_rate")
    income = model_input["financial_statements"].get("income_statement", {})
    ebitda = _decimal(income.get("ebitda", [None])[-1], "historical EBITDA")
    debt = _decimal(a.get("opening_debt"), "opening_debt")
    rows = []
    for period in _forecast_periods(model_input["periods"][-1], horizon):
        ebitda *= Decimal(1) + growth
        interest = debt * rate
        payment = min(repayment, debt)
        debt_service = interest + payment
        closing = debt - payment
        leverage = closing / ebitda if ebitda else Decimal("Infinity")
        dscr = ebitda / debt_service if debt_service else Decimal("Infinity")
        rows.append({"period": period, "opening_debt": _money(debt), "interest": _money(interest), "repayment": _money(payment), "closing_debt": _money(closing), "ebitda": _money(ebitda), "leverage_ratio": str(leverage.quantize(Decimal("0.0001"))), "debt_service_coverage": str(dscr.quantize(Decimal("0.0001"))), "covenant_pass": leverage <= max_leverage and dscr >= min_dscr})
        debt = closing
    return {"contract_version": "debt-capacity-refinancing-result.v1", "forecast": rows, "all_covenants_pass": all(row["covenant_pass"] for row in rows)}


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def calculate_forecast(model_input: dict[str, Any]) -> dict[str, Any]:
    assumptions = model_input["assumptions"]
    horizon = _positive_int(assumptions.get("forecast_horizon"), "forecast_horizon")
    scenario = assumptions.get("scenario")
    if scenario not in {"base", "upside", "downside"}:
        raise ValueError("scenario must be base, upside or downside")
    adjustments = assumptions.get("scenario_adjustments")
    if not isinstance(adjustments, dict) or not isinstance(adjustments.get(scenario), dict):
        raise ValueError("scenario_adjustments must explicitly define the selected scenario")
    selected = adjustments[scenario]
    revenue_rate = _decimal(assumptions.get("revenue_growth_rate"), "revenue_growth_rate") + _decimal(selected.get("revenue_growth_delta"), "revenue_growth_delta")
    cost_rate = _decimal(assumptions.get("operating_cost_growth_rate"), "operating_cost_growth_rate") + _decimal(selected.get("operating_cost_growth_delta"), "operating_cost_growth_delta")
    statement = model_input["financial_statements"].get("income_statement", {})
    revenue = _decimal(statement.get("revenue", [None])[-1], "historical revenue")
    costs = _decimal(statement.get("operating_costs", [None])[-1], "historical operating costs")
    periods = _forecast_periods(model_input["periods"][-1], horizon)
    rows = []
    for period in periods:
        revenue *= Decimal(1) + revenue_rate
        costs *= Decimal(1) + cost_rate
        rows.append({"period": period, "revenue": str(revenue.quantize(Decimal("0.01"))), "operating_costs": str(costs.quantize(Decimal("0.01"))), "operating_profit": str((revenue - costs).quantize(Decimal("0.01")))})
    return {"contract_version": "budget-forecast-result.v1", "scenario": scenario, "actual_periods": model_input["periods"], "forecast_periods": periods, "forecast": rows}


def calculate_saas_forecast(model_input: dict[str, Any]) -> dict[str, Any]:
    assumptions = model_input["assumptions"]
    horizon = _positive_int(assumptions.get("forecast_horizon"), "forecast_horizon")
    scenario = assumptions.get("scenario")
    if scenario not in {"base", "upside", "downside"}:
        raise ValueError("scenario must be base, upside or downside")
    adjustments = assumptions.get("saas_scenario_adjustments")
    if not isinstance(adjustments, dict) or not isinstance(adjustments.get(scenario), dict):
        raise ValueError("saas_scenario_adjustments must explicitly define the selected scenario")
    selected = adjustments[scenario]
    mrr_growth = _rate(assumptions.get("monthly_recurring_revenue_growth_rate"), "monthly_recurring_revenue_growth_rate", minimum=Decimal("-1"), maximum=None) + _decimal(selected.get("mrr_growth_delta"), "mrr_growth_delta")
    customer_growth = _rate(assumptions.get("customer_growth_rate"), "customer_growth_rate", maximum=None) + _decimal(selected.get("customer_growth_delta"), "customer_growth_delta")
    churn = _rate(assumptions.get("customer_churn_rate"), "customer_churn_rate") + _decimal(selected.get("churn_rate_delta"), "churn_rate_delta")
    gross_margin = _rate(assumptions.get("gross_margin_rate"), "gross_margin_rate")
    if not Decimal("0") <= churn <= Decimal("1"):
        raise ValueError("scenario-adjusted customer churn rate must be between zero and one")
    if mrr_growth <= Decimal("-1") or customer_growth < Decimal("0"):
        raise ValueError("scenario-adjusted SaaS growth rates are invalid")
    drivers = model_input["operational_drivers"]
    mrr = _decimal(drivers.get("monthly_recurring_revenue", [None])[-1], "monthly recurring revenue")
    customers = _decimal(drivers.get("customer_count", [None])[-1], "customer count")
    periods = _forecast_periods(model_input["periods"][-1], horizon)
    rows = []
    for period in periods:
        beginning_customers = customers
        new_customers = beginning_customers * customer_growth
        churned_customers = beginning_customers * churn
        customers = beginning_customers + new_customers - churned_customers
        mrr *= Decimal("1") + mrr_growth
        arr = mrr * Decimal("12")
        rows.append({
            "period": period,
            "monthly_recurring_revenue": str(mrr.quantize(Decimal("0.01"))),
            "annual_recurring_revenue": str(arr.quantize(Decimal("0.01"))),
            "customer_count": str(customers.quantize(Decimal("0.01"))),
            "new_customers": str(new_customers.quantize(Decimal("0.01"))),
            "churned_customers": str(churned_customers.quantize(Decimal("0.01"))),
            "average_revenue_per_customer": str((mrr / customers).quantize(Decimal("0.01"))) if customers > 0 else "0.00",
            "gross_profit": str((arr * gross_margin).quantize(Decimal("0.01"))),
        })
    return {"contract_version": "saas-budget-forecast-result.v1", "scenario": scenario, "actual_periods": model_input["periods"], "forecast_periods": periods, "forecast": rows}


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{name} must be a decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    return result


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _rate(value: Any, name: str, *, minimum: Decimal = Decimal("0"), maximum: Decimal | None = Decimal("1")) -> Decimal:
    result = _decimal(value, name)
    if result < minimum or (maximum is not None and result > maximum):
        boundary = f"between {minimum} and {maximum}" if maximum is not None else f"at least {minimum}"
        raise ValueError(f"{name} must be {boundary}")
    return result


def _forecast_periods(last: str, count: int) -> list[str]:
    if last.isdigit() and len(last) == 4:
        return [str(int(last) + offset) for offset in range(1, count + 1)]
    return [f"Forecast {offset}" for offset in range(1, count + 1)]
