from __future__ import annotations

import base64
import unittest

from fastapi.testclient import TestClient

from fmr.api.composed import create_app
from tests.calculation_case import populated_execution_case


class WorkbookCalculationApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())

    def test_external_acceptance_endpoint_returns_value_free_receipt(self) -> None:
        populated, write_plan, execution_receipt = populated_execution_case()
        encoded = base64.b64encode(populated).decode("ascii")
        response = self.client.post(
            "/api/v1/workbooks/calculation-acceptances",
            json={
                "contract_version": "external-calculation-acceptance-request.v1",
                "input_filename": "populated.xlsx",
                "output_filename": "uncalculated.xlsx",
                "input_workbook_base64": encoded,
                "calculated_workbook_base64": encoded,
                "write_plan": write_plan,
                "execution_receipt": execution_receipt,
                "engine_name": "external-test-engine",
                "engine_version": "test-only",
            },
        )
        self.assertEqual(response.status_code, 200)
        acceptance = response.json()
        self.assertEqual(
            acceptance["contract_version"],
            "workbook-calculation-acceptance.v1",
        )
        self.assertEqual(acceptance["status"], "failed")
        self.assertGreater(
            acceptance["summary"]["missing_cached_value_count"],
            0,
        )

        validation = self.client.post(
            "/api/v1/workbooks/calculation-acceptances/validate",
            json={
                "acceptance": acceptance,
                "write_plan": write_plan,
                "execution_receipt": execution_receipt,
            },
        )
        self.assertEqual(validation.status_code, 200)
        self.assertEqual(validation.json(), {"valid": True, "issues": []})

    def test_engine_status_endpoint_is_explicit(self) -> None:
        response = self.client.get("/api/v1/calculation-engine")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("available", payload)
        self.assertIn("engine", payload)
        self.assertIn("error", payload)

    def test_external_acceptance_rejects_path_like_filename(self) -> None:
        populated, write_plan, execution_receipt = populated_execution_case()
        encoded = base64.b64encode(populated).decode("ascii")
        response = self.client.post(
            "/api/v1/workbooks/calculation-acceptances",
            json={
                "contract_version": "external-calculation-acceptance-request.v1",
                "input_filename": "../populated.xlsx",
                "output_filename": "uncalculated.xlsx",
                "input_workbook_base64": encoded,
                "calculated_workbook_base64": encoded,
                "write_plan": write_plan,
                "execution_receipt": execution_receipt,
                "engine_name": "external-test-engine",
                "engine_version": "test-only",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_calculation_browser_asset_is_served(self) -> None:
        response = self.client.get("/assets/calculation.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("calculateOutput", response.text)


if __name__ == "__main__":
    unittest.main()
