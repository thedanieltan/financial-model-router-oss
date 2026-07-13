from __future__ import annotations

import base64
import unittest

from fastapi.testclient import TestClient

from fmr.api.composed import create_app
from tests.input_population_case import input_population_case


class WorkbookInputPopulationApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())

    def test_compile_populate_validate_and_link_endpoints(self) -> None:
        executed, write_plan, execution_receipt, _, csv_bytes = (
            input_population_case()
        )
        compiled = self.client.post(
            "/api/v1/workbooks/input-sets/from-csv",
            json={
                "contract_version": "workbook-input-set-csv-request.v1",
                "source_name": "inputs.csv",
                "csv_base64": base64.b64encode(csv_bytes).decode("ascii"),
                "write_plan": write_plan,
                "execution_receipt": execution_receipt,
            },
        )
        self.assertEqual(compiled.status_code, 200)
        input_set = compiled.json()
        self.assertEqual(input_set["contract_version"], "workbook-input-set.v1")

        validation = self.client.post(
            "/api/v1/workbooks/input-sets/validate",
            json={
                "input_set": input_set,
                "write_plan": write_plan,
                "execution_receipt": execution_receipt,
            },
        )
        self.assertEqual(validation.status_code, 200)
        self.assertEqual(validation.json(), {"valid": True, "issues": []})

        populated = self.client.post(
            "/api/v1/workbooks/input-populations",
            json={
                "contract_version": "workbook-input-population-request.v1",
                "filename": "executed.xlsx",
                "output_filename": "populated.xlsx",
                "workbook_base64": base64.b64encode(executed).decode("ascii"),
                "write_plan": write_plan,
                "execution_receipt": execution_receipt,
                "input_set": input_set,
            },
        )
        self.assertEqual(populated.status_code, 200)
        result = populated.json()
        self.assertEqual(
            result["contract_version"], "workbook-input-population-result.v1"
        )
        self.assertTrue(base64.b64decode(result["workbook_base64"], validate=True))
        receipt = result["receipt"]

        receipt_validation = self.client.post(
            "/api/v1/workbooks/input-population-receipts/validate",
            json={
                "receipt": receipt,
                "input_set": input_set,
                "write_plan": write_plan,
                "execution_receipt": execution_receipt,
            },
        )
        self.assertEqual(receipt_validation.status_code, 200)
        self.assertEqual(
            receipt_validation.json(), {"valid": True, "issues": []}
        )

        acceptance = {
            "contract_version": "workbook-calculation-acceptance.v1",
            "write_plan_id": receipt["write_plan_id"],
            "write_plan_sha256": receipt["write_plan_sha256"],
            "execution_id": receipt["execution_id"],
            "execution_receipt_sha256": receipt[
                "execution_receipt_sha256"
            ],
            "input": receipt["output"],
        }
        link = self.client.post(
            "/api/v1/workbooks/input-population-receipts/validate-calculation-link",
            json={
                "population_receipt": receipt,
                "calculation_acceptance": acceptance,
            },
        )
        self.assertEqual(link.status_code, 200)
        self.assertEqual(link.json(), {"valid": True, "issues": []})

    def test_population_rejects_path_like_filename(self) -> None:
        executed, write_plan, execution_receipt, input_set, _ = (
            input_population_case()
        )
        response = self.client.post(
            "/api/v1/workbooks/input-populations",
            json={
                "contract_version": "workbook-input-population-request.v1",
                "filename": "../executed.xlsx",
                "output_filename": "populated.xlsx",
                "workbook_base64": base64.b64encode(executed).decode("ascii"),
                "write_plan": write_plan,
                "execution_receipt": execution_receipt,
                "input_set": input_set,
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_population_rejects_invalid_base64(self) -> None:
        _, write_plan, execution_receipt, input_set, _ = input_population_case()
        response = self.client.post(
            "/api/v1/workbooks/input-populations",
            json={
                "contract_version": "workbook-input-population-request.v1",
                "filename": "executed.xlsx",
                "output_filename": "populated.xlsx",
                "workbook_base64": "not-base64!",
                "write_plan": write_plan,
                "execution_receipt": execution_receipt,
                "input_set": input_set,
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_input_population_browser_asset_is_served(self) -> None:
        response = self.client.get("/assets/input_population.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("populateInputs", response.text)
        self.assertIn("/api/v1/workbooks/input-populations", response.text)


if __name__ == "__main__":
    unittest.main()
