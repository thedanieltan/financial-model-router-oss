from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fmr.core import ModelJob, route_job
from fmr.core.receipts import validate_execution_result
from fmr.execution import ExecutionOrchestrator, SqliteExecutionLedger
from fmr.provider_service import prepare_handoff
from fmr.vocabulary import IndustryVocabulary, VocabularyRegistry


def _saas_case(root: Path) -> tuple[dict, dict]:
    source = root / "saas-canonical.json"
    source.write_text(json.dumps({
        "contract_version": "canonical-financial-data.v2",
        "entity": {"entity_id": "synthetic-saas", "currency": "USD"},
        "periods": ["2025", "2026"],
        "financial_statements": {"income_statement": {"revenue": ["12000", "13200"], "operating_costs": ["5000", "5400"]}},
        "trial_balance": [], "account_balances": [], "debt_schedules": [], "capital_expenditure": [], "working_capital": [],
        "operational_drivers": {"monthly_recurring_revenue": ["1000", "1100"], "customer_count": ["100", "110"]},
        "assumptions": {
            "forecast_horizon": 2, "monthly_recurring_revenue_growth_rate": "0.10", "customer_growth_rate": "0.15",
            "customer_churn_rate": "0.05", "gross_margin_rate": "0.80", "scenario": "upside",
            "saas_scenario_adjustments": {"upside": {"mrr_growth_delta": "0.02", "customer_growth_delta": "0.02", "churn_rate_delta": "-0.01"}}
        },
        "provenance": [{"source": "synthetic-saas-test"}],
    }), encoding="utf-8")
    reference = {"contract_version": "canonical-financial-data.v2", "path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    job = {
        "contract_version": "model-job.v2", "objective": "Prepare a SaaS budget and unit-economics forecast",
        "model_family": "budget_forecast", "industry": "software as a service",
        "requested_deliverables": ["budget_forecast", "saas_unit_economics"],
        "available_data": ["customer_history", "income_statement_history", "monthly_recurring_revenue_history"],
        "available_assumptions": ["customer_churn_rate", "customer_growth_rate", "forecast_horizon", "gross_margin_rate", "monthly_recurring_revenue_growth_rate", "saas_scenario_adjustments", "scenario"],
        "input_references": {"canonical_financial_data": reference}, "output_formats": ["json"],
        "constraints": {"local_only": True, "open_source_only": True},
    }
    return job, reference


class IndustryExtensionTests(unittest.TestCase):
    def test_eight_declarative_vocabularies_load_without_provider_code(self) -> None:
        registry = VocabularyRegistry.builtins()
        self.assertEqual([item.vocabulary_id for item in registry.vocabularies], ["banking", "core-financials", "energy", "hospitality", "insurance", "logistics", "real-estate", "saas"])
        self.assertEqual(registry.normalize_industry("Software as a Service"), "saas")
        self.assertEqual(registry.normalize_industry("Property Development"), "real_estate")
        self.assertIn("monthly_recurring_revenue", registry.concept_ids("saas"))

    def test_vocabulary_validation_rejects_normalized_alias_collisions(self) -> None:
        payload = VocabularyRegistry.builtins().vocabularies[-1].to_dict()
        payload["aliases"] = ["Software as a Service", "software-as-a-service"]
        with self.assertRaisesRegex(ValueError, "normalized vocabulary aliases"):
            IndustryVocabulary.from_mapping(payload)

    def test_saas_package_is_selected_and_executes_specialist_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, _ = _saas_case(root)
            self.assertEqual(ModelJob.from_mapping(job).industry, "saas")
            decision = route_job(job)
            self.assertEqual(decision["selected"]["package_id"], "python-forecast/saas-budget-forecast")
            self.assertEqual(decision["missing_requirements"], [])
            handoff = prepare_handoff(job)
            orchestrator = ExecutionOrchestrator(ledger=SqliteExecutionLedger(root / "ledger.sqlite3"), managed_output_root=root / "outputs")
            result = orchestrator.execute(handoff, idempotency_key="saas", output_dir=root / "outputs")
            self.assertEqual(result["state"], "completed")
            self.assertEqual(validate_execution_result(result, handoff=handoff), ())
            forecast = json.loads(Path(result["output_artifact_references"][0]["path"]).read_text())
            self.assertEqual(forecast["contract_version"], "saas-budget-forecast-result.v1")
            self.assertEqual(forecast["forecast"][0]["monthly_recurring_revenue"], "1232.00")
            self.assertEqual(forecast["forecast"][0]["customer_count"], "124.30")
            self.assertEqual(forecast["forecast"][0]["gross_profit"], "11827.20")


if __name__ == "__main__":
    unittest.main()
