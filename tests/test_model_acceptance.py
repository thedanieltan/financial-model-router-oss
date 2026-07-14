from __future__ import annotations

import copy
import json
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path

from fmr.acceptance import run_acceptance_corpus, validate_acceptance_corpus
from fmr.entrypoint import main
from tests.test_model_family_packages import _canonical


def _corpus() -> dict:
    assumptions = ["capital_expenditure_rate", "depreciation_rate", "discount_rate", "forecast_horizon", "net_debt", "operating_margin_rate", "revenue_growth_rate", "tax_rate", "terminal_growth_rate", "terminal_value_assumption", "working_capital_rate"]
    return {"contract_version": "model-acceptance-corpus.v1", "corpus_id": "synthetic-dcf-v1", "cases": [{"case_id": "dcf-base", "data_classification": "synthetic", "job": {"contract_version": "model-job.v2", "objective": "Synthetic DCF acceptance", "model_family": "operating_company_dcf", "requested_deliverables": ["enterprise_value", "equity_value", "operating_forecast"], "available_data": ["capital_expenditure", "cash_flow_history", "income_statement_history", "net_debt", "revenue_drivers", "working_capital"], "available_assumptions": assumptions, "input_references": {}, "output_formats": ["json"]}, "canonical_input": _canonical(), "assertions": [{"assertion_id": "contract", "path": "/contract_version", "operator": "equals", "expected": "operating-company-dcf-result.v1"}, {"assertion_id": "positive-enterprise-value", "path": "/enterprise_value", "operator": "greater_than_or_equal", "expected": "0"}]}], "practitioner_reviews": []}


class ModelAcceptanceTests(unittest.TestCase):
    def test_bundled_corpus_covers_every_executable_python_package(self) -> None:
        path = files("fmr.fixtures").joinpath("acceptance/synthetic-initial-families.v1.json")
        corpus = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(validate_acceptance_corpus(corpus), ())
        result = run_acceptance_corpus(corpus)
        self.assertEqual(result["implementation_status"], "passed")
        self.assertEqual(result["production_status"], "not_accepted")
        self.assertEqual(
            {item["package_id"] for item in result["case_results"]},
            {
                "python-forecast/generic-budget-forecast",
                "python-forecast/saas-budget-forecast",
                "python-forecast/integrated-three-statement",
                "python-forecast/operating-company-dcf",
                "python-forecast/debt-capacity-refinancing",
            },
        )
        self.assertTrue(all(item["status"] == "passed" for item in result["case_results"]))

    def test_synthetic_corpus_passes_implementation_but_not_production(self) -> None:
        corpus = _corpus()
        self.assertEqual(validate_acceptance_corpus(corpus), ())
        result = run_acceptance_corpus(corpus)
        self.assertEqual(result["implementation_status"], "passed")
        self.assertEqual(result["practitioner_status"], "pending")
        self.assertEqual(result["production_status"], "not_accepted")
        self.assertNotIn("actual", json.dumps(result).lower())
        self.assertEqual(result, run_acceptance_corpus(corpus))

    def test_anonymized_case_and_review_can_complete_evidence_ledger(self) -> None:
        corpus = _corpus()
        corpus["cases"][0]["data_classification"] = "anonymized"
        corpus["practitioner_reviews"] = [{"model_family": "operating_company_dcf", "reviewer_role": "qualified-finance-practitioner", "status": "accepted", "evidence_reference": "review://external-immutable-record"}]
        result = run_acceptance_corpus(corpus)
        self.assertEqual(result["production_status"], "accepted")

    def test_bad_assertion_fails_case(self) -> None:
        corpus = _corpus()
        corpus["cases"][0]["assertions"][1]["expected"] = "999999999"
        self.assertEqual(run_acceptance_corpus(corpus)["implementation_status"], "failed")

    def test_cli_preserves_practitioner_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, output = root / "corpus.json", root / "result.json"
            path.write_text(json.dumps(_corpus()), encoding="utf-8")
            self.assertEqual(main(["run-acceptance-corpus", str(path), "--output", str(output)]), 0)
            self.assertEqual(main(["run-acceptance-corpus", str(path), "--require-practitioner", "--output", str(output)]), 2)


if __name__ == "__main__":
    unittest.main()
