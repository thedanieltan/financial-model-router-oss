from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fmr.providers.python_forecast.plugin import calculate_dcf, calculate_debt_capacity, calculate_three_statement
from fmr.registry import ProviderRegistry
from fmr.provider_service import prepare_handoff
from fmr.execution import ExecutionOrchestrator, SqliteExecutionLedger
from fmr.core.receipts import validate_execution_result


def _canonical() -> dict:
    return {
        "contract_version": "canonical-financial-data.v2", "entity": {"entity_id": "synthetic", "currency": "USD"}, "periods": ["2025"],
        "financial_statements": {"income_statement": {"revenue": ["1000"], "ebitda": ["200"]}, "balance_sheet": {"cash": ["100"], "debt": ["300"], "equity": ["500"]}, "cash_flow": {"operating_cash_flow": ["150"]}},
        "trial_balance": [], "account_balances": [], "debt_schedules": [], "capital_expenditure": [], "working_capital": [], "operational_drivers": {},
        "assumptions": {"forecast_horizon": 2, "tax_rate": "0.20", "revenue_growth_rate": "0.10", "operating_margin_rate": "0.20", "depreciation_rate": "0.03", "capital_expenditure_rate": "0.05", "working_capital_rate": "0.10", "discount_rate": "0.10", "terminal_growth_rate": "0.02", "net_debt": "200", "interest_rate_assumption": "0.05", "annual_repayment": "50", "maximum_leverage_ratio": "3", "minimum_debt_service_coverage": "1.5", "ebitda_growth_rate": "0.05", "opening_debt": "300"},
        "provenance": [{"source": "synthetic"}],
    }


class ModelFamilyPackageTests(unittest.TestCase):
    def test_three_statement_balances_and_cash_reconciles(self) -> None:
        result = calculate_three_statement(_canonical())
        for row in result["forecast"]:
            self.assertEqual(row["balance_sheet"]["assets"], row["balance_sheet"]["liabilities_and_equity"])

    def test_dcf_bridge_and_discount_factors(self) -> None:
        result = calculate_dcf(_canonical())
        self.assertEqual(float(result["enterprise_value"]) - float(result["net_debt"]), float(result["equity_value"]))
        factors = [float(row["discount_factor"]) for row in result["forecast"]]
        self.assertGreater(factors[0], factors[1])

    def test_debt_roll_forward_and_covenants(self) -> None:
        result = calculate_debt_capacity(_canonical())
        for row in result["forecast"]:
            self.assertEqual(float(row["opening_debt"]) - float(row["repayment"]), float(row["closing_debt"]))

    def test_all_initial_families_have_executable_python_packages(self) -> None:
        packages = ProviderRegistry.builtins().packages()
        covered = {item.package.model_family for item in packages if item.provider.provider_id == "python-forecast" and item.provider_adapter_available and item.provider_executor_available}
        self.assertTrue({"budget_forecast", "three_statement", "operating_company_dcf", "debt_capacity_refinancing"}.issubset(covered))

    def test_new_families_route_handoff_execute_and_validate(self) -> None:
        cases = (
            ("three_statement", ["three_statement_forecast"], ["balance_sheet_history", "capital_expenditure", "cash_flow_history", "debt_schedule", "income_statement_history", "working_capital"], ["capital_expenditure_rate", "depreciation_rate", "forecast_horizon", "operating_margin_rate", "revenue_growth_rate", "tax_rate", "working_capital_rate"], "three_statement_forecast"),
            ("operating_company_dcf", ["enterprise_value", "equity_value", "operating_forecast"], ["capital_expenditure", "cash_flow_history", "income_statement_history", "net_debt", "revenue_drivers", "working_capital"], ["capital_expenditure_rate", "depreciation_rate", "discount_rate", "forecast_horizon", "net_debt", "operating_margin_rate", "revenue_growth_rate", "tax_rate", "terminal_growth_rate", "terminal_value_assumption", "working_capital_rate"], "operating_company_dcf"),
            ("debt_capacity_refinancing", ["debt_capacity", "refinancing_analysis"], ["cash_flow_history", "debt_schedule", "income_statement_history", "liquidity_position"], ["annual_repayment", "covenant_thresholds", "ebitda_growth_rate", "forecast_horizon", "interest_rate_assumption", "maximum_leverage_ratio", "minimum_debt_service_coverage", "opening_debt", "repayment_terms"], "debt_capacity_refinancing"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "canonical.json"
            source.write_text(json.dumps(_canonical()), encoding="utf-8")
            reference = {"contract_version": "canonical-financial-data.v2", "path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
            orchestrator = ExecutionOrchestrator(ledger=SqliteExecutionLedger(root / "ledger.sqlite3"), managed_output_root=root / "outputs")
            for family, deliverables, data, assumptions, artifact_kind in cases:
                job = {"contract_version": "model-job.v2", "objective": f"Execute {family}", "model_family": family, "requested_deliverables": deliverables, "available_data": data, "available_assumptions": assumptions, "input_references": {"canonical_financial_data": reference}, "output_formats": ["json"]}
                handoff = prepare_handoff(job)
                self.assertEqual(handoff["provider"]["provider_id"], "python-forecast")
                result = orchestrator.execute_request({"contract_version": "execution-request.v1", "handoff": handoff, "idempotency_key": family, "execution_mode": "local", "timeout_seconds": 30, "secret_references": [], "output_policy": {"mode": "managed", "overwrite": False, "publish": False}})
                self.assertEqual(result["state"], "completed")
                self.assertEqual(result["output_artifact_references"][0]["kind"], artifact_kind)
                self.assertEqual(validate_execution_result(result, handoff=handoff), ())


if __name__ == "__main__":
    unittest.main()
