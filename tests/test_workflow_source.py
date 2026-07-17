from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from fmr.api.composed import create_app
from fmr.data import validate_canonical_financial_data
from fmr.financial_data import (
    WorkflowSourceStore,
    compile_canonical_financial_data,
    create_statement_csv_workflow_source,
    statement_csv_template,
)
from fmr.workflow import compile_workflow, execute_workflow
from tests.financial_data_case import financial_data_case, statement_csv_bytes


ASSUMPTIONS = {
    "forecast_horizon": 3,
    "operating_cost_growth_rate": "0.05",
    "revenue_growth_rate": "0.08",
    "scenario": "base",
    "scenario_adjustments": {
        "base": {
            "operating_cost_growth_delta": "0",
            "revenue_growth_delta": "0",
        }
    },
}

MAPPING_RULES = [
    {
        "account_code": "6000",
        "account_name": None,
        "concept_id": "operating_costs",
    }
]


class WorkflowSourceTests(unittest.TestCase):
    def test_mapping_compiles_canonical_data_without_inventing_unmapped_rows(self) -> None:
        package, _, mapping, _, _, _ = financial_data_case()
        canonical = compile_canonical_financial_data(
            package,
            mapping,
            assumptions=ASSUMPTIONS,
        )
        self.assertEqual(validate_canonical_financial_data(canonical), ())
        self.assertEqual(
            canonical["financial_statements"]["income_statement"]["revenue"],
            ["100", "110", "120", "130", "140", "150", "160"],
        )
        self.assertEqual(
            canonical["financial_statements"]["income_statement"]["operating_costs"],
            ["40", "44", "48", "52", "56", "60", "64"],
        )
        self.assertNotIn("support_tickets", canonical["operational_drivers"])
        self.assertEqual(canonical["assumptions"], ASSUMPTIONS)

    def test_source_store_is_immutable_and_returns_value_free_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = create_statement_csv_workflow_source(
                statement_csv_bytes(),
                source_name="synthetic-statements.csv",
                mapping_rules=MAPPING_RULES,
                assumptions=ASSUMPTIONS,
                store=WorkflowSourceStore(temporary),
            )
            reference = result["canonical_reference"]
            path = Path(reference["path"])
            self.assertTrue(path.is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), reference["sha256"])
            self.assertEqual(result["available_data"], ["income_statement_history"])
            self.assertEqual(result["available_assumptions"], sorted(ASSUMPTIONS))
            self.assertEqual(result["mapping"]["unmapped_row_count"], 7)
            self.assertEqual(len(result["warnings"]), 7)
            self.assertNotIn("financial_statements", result)
            repeated = create_statement_csv_workflow_source(
                statement_csv_bytes(),
                source_name="synthetic-statements.csv",
                mapping_rules=MAPPING_RULES,
                assumptions=ASSUMPTIONS,
                store=WorkflowSourceStore(temporary),
            )
            self.assertEqual(result, repeated)

    def test_uploaded_source_routes_and_executes_budget_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = create_statement_csv_workflow_source(
                statement_csv_bytes(include_unmapped=False),
                source_name="synthetic-statements.csv",
                mapping_rules=MAPPING_RULES,
                assumptions=ASSUMPTIONS,
                store=WorkflowSourceStore(Path(temporary) / "sources"),
            )
            request = {
                "contract_version": "finance-workflow-request.v1",
                "objective": "Update the full year forecast using actuals",
                "role": "fp_and_a",
                "entity_id": source["entity"]["entity_id"],
                "reporting_period": source["periods"][-1],
                "requested_outputs": ["rolling_forecast", "management_pack"],
                "available_data": [
                    *source["available_data"],
                    "operating_cost_drivers",
                    "revenue_drivers",
                ],
                "available_assumptions": source["available_assumptions"],
                "input_references": {
                    "canonical_financial_data": source["canonical_reference"]
                },
                "industry": None,
                "output_formats": ["json"],
                "policy_name": "json-first",
                "constraints": {
                    "local_only": True,
                    "open_source_only": True,
                    "network_allowed": False,
                },
                "context": {"workflow_source_id": source["source_id"]},
            }
            plan = compile_workflow(request)
            forecast_step = next(
                item for item in plan["steps"] if item["step_id"] == "refresh_forecast"
            )
            self.assertEqual(forecast_step["status"], "ready")
            self.assertEqual(
                forecast_step["route_decision"]["selected"]["provider_id"],
                "python-forecast",
            )
            result = execute_workflow(
                plan,
                idempotency_key="source-workflow",
                output_dir=Path(temporary) / "outputs",
                approvals={"review_forecast": True},
            )
            self.assertEqual(result["state"], "completed")
            executed = next(
                item for item in result["step_results"] if item["step_id"] == "refresh_forecast"
            )
            self.assertEqual(executed["state"], "completed")

    def test_http_upload_and_template_are_practitioner_ready(self) -> None:
        client = TestClient(create_app())
        template = client.get("/api/v2/workflow-sources/statement-csv-template")
        self.assertEqual(template.status_code, 200)
        self.assertEqual(template.content, statement_csv_template())
        self.assertIn("attachment", template.headers["content-disposition"])
        response = client.post(
            "/api/v2/workflow-sources/statement-csv",
            json={
                "contract_version": "workflow-statement-csv-request.v1",
                "source_name": "synthetic-statements.csv",
                "csv_base64": base64.b64encode(statement_csv_bytes()).decode("ascii"),
                "mapping_rules": MAPPING_RULES,
                "assumptions": ASSUMPTIONS,
                "operational_drivers": {},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        schema = json.loads(
            files("fmr.contracts")
            .joinpath("workflow-source-result.v1.schema.json")
            .read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(result)
        self.assertTrue(result["ready"])
        self.assertTrue(Path(result["canonical_reference"]["path"]).is_file())

    def test_incomplete_mapped_series_fail_closed(self) -> None:
        package, _, mapping, _, _, _ = financial_data_case()
        mapping["concept_series"] = mapping["concept_series"][:-1]
        mapping["mapping_id"] = "fmrm_" + "0" * 24
        with self.assertRaisesRegex(ValueError, "mapping_id does not match payload"):
            compile_canonical_financial_data(package, mapping, assumptions=ASSUMPTIONS)


if __name__ == "__main__":
    unittest.main()
