from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from fmr.api.app import MAX_REQUEST_BYTES, MAX_WORKBOOK_REQUEST_BYTES, create_app
from fmr.fixtures import load_fixture
from fmr.plan import build_plan
from fmr.router import route_request
from fmr.types import ModelRequest
from fmr.workbook import inspect_workbook_bytes
from tests.xlsx_factory import financial_workbook


class DeveloperApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())

    def test_health_and_workbench_load(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertEqual(health.json()["service"], "financial-model-router")

        workbench = self.client.get("/")
        self.assertEqual(workbench.status_code, 200)
        self.assertIn("Developer Workbench", workbench.text)
        self.assertIn("Workbook inspection", workbench.text)
        self.assertIn("/assets/app.js", workbench.text)

    def test_model_families_and_fixtures_are_discoverable(self) -> None:
        families = self.client.get("/api/v1/model-families")
        self.assertEqual(families.status_code, 200)
        family_ids = {item["model_family"] for item in families.json()}
        self.assertEqual(
            family_ids,
            {
                "budget_forecast",
                "three_statement",
                "operating_company_dcf",
                "debt_capacity_refinancing",
            },
        )

        fixtures = self.client.get("/api/v1/fixtures")
        self.assertEqual(fixtures.status_code, 200)
        fixture_ids = {item["fixture_id"] for item in fixtures.json()}
        self.assertEqual(fixture_ids, {"dcf-ready", "debt-blocked"})

    def test_route_endpoint_matches_core_exactly(self) -> None:
        payload = load_fixture("dcf-ready")
        core = route_request(ModelRequest.from_mapping(payload)).to_dict()
        response = self.client.post("/api/v1/route", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), core)

    def test_plan_endpoint_matches_core_exactly(self) -> None:
        payload = load_fixture("debt-blocked")
        core = build_plan(ModelRequest.from_mapping(payload)).to_dict()
        response = self.client.post("/api/v1/plan", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), core)
        self.assertFalse(response.json()["ready_to_apply"])
        self.assertEqual(
            response.json()["operations"][0]["operation"],
            "request_missing_inputs",
        )

    def test_validate_plan_reports_core_issues(self) -> None:
        plan = build_plan(ModelRequest.from_mapping(load_fixture("dcf-ready"))).to_dict()
        valid = self.client.post("/api/v1/validate-plan", json=plan)
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json(), {"valid": True, "issues": []})

        plan["operations"][0]["formula"] = "=1+1"
        invalid = self.client.post("/api/v1/validate-plan", json=plan)
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(invalid.json()["valid"])
        self.assertIn(
            "operations[0] contains executable workbook fields",
            invalid.json()["issues"],
        )

    def test_unknown_objective_returns_structured_422(self) -> None:
        payload = load_fixture("dcf-ready")
        payload["objective"] = "write a marketing plan"
        response = self.client.post("/api/v1/route", json=payload)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "invalid_model_request")

    def test_request_contract_rejects_extra_fields(self) -> None:
        payload = load_fixture("dcf-ready")
        payload["workbook_bytes"] = "not allowed"
        response = self.client.post("/api/v1/route", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_declared_oversized_request_is_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/route",
            content=b"{}",
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(MAX_REQUEST_BYTES + 1),
            },
        )
        self.assertEqual(response.status_code, 413)
        self.assertFalse(response.json()["valid"])

    def test_workbook_inspection_matches_core_exactly(self) -> None:
        data = financial_workbook()
        core = inspect_workbook_bytes(data, filename="synthetic.xlsx").to_dict()
        response = self.client.post(
            "/api/v1/workbooks/inspect?filename=synthetic.xlsx",
            content=data,
            headers={
                "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), core)

    def test_workbook_inspection_rejects_unsupported_extension(self) -> None:
        response = self.client.post(
            "/api/v1/workbooks/inspect?filename=synthetic.xlsm",
            content=financial_workbook(),
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "invalid_workbook")

    def test_declared_oversized_workbook_is_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/workbooks/inspect?filename=synthetic.xlsx",
            content=b"x",
            headers={"Content-Length": str(MAX_WORKBOOK_REQUEST_BYTES + 1)},
        )
        self.assertEqual(response.status_code, 413)
        self.assertFalse(response.json()["valid"])


if __name__ == "__main__":
    unittest.main()
