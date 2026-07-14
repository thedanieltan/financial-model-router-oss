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


class PythonForecastExecutor:
    def execute(self, handoff: dict[str, Any], output_dir: Path, secrets: dict[str, str]) -> dict[str, Any]:
        if secrets:
            raise ValueError("Python Forecast does not accept secrets")
        package_id = handoff.get("package", {}).get("package_id")
        if handoff.get("provider", {}).get("provider_id") != "python-forecast" or package_id not in {"python-forecast/generic-budget-forecast", "python-forecast/saas-budget-forecast"}:
            raise ValueError("handoff is not assigned to the Python Forecast budget package")
        reference = handoff["provider_payload"]["canonical_financial_data"]
        source = Path(reference["path"])
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
            raise ValueError("canonical model input hash mismatch")
        model_input = json.loads(raw)
        issues = validate_canonical_model_input(model_input)
        if issues:
            raise ValueError("invalid canonical model input: " + "; ".join(issues))
        is_saas = package_id == "python-forecast/saas-budget-forecast"
        result = calculate_saas_forecast(model_input) if is_saas else calculate_forecast(model_input)
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
            "output_artifacts": [{"kind": "saas_budget_forecast" if is_saas else "budget_forecast", "format": "json", "path": str(output), "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}],
            "validation": {"status": "passed", "checks": ["period_continuity", "saas_metric_reconciliation" if is_saas else "forecast_reconciliation", "scenario_applied"]},
        }


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
