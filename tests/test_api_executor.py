from __future__ import annotations

import base64
import unittest

from fastapi.testclient import TestClient

from fmr.api.composed import create_app
from fmr.workbook import validate_workbook_execution_receipt_payload
from tests.test_executor import execution_case


class WorkbookExecutorApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())

    def test_execution_endpoint_returns_copy_and_receipt(self) -> None:
        source_bytes, write_plan = execution_case()
        response = self.client.post(
            "/api/v1/workbooks/executions",
            json={
                "contract_version": "workbook-execution-request.v1",
                "filename": "synthetic.xlsx",
                "output_filename": "completed.xlsx",
                "workbook_base64": base64.b64encode(source_bytes).decode("ascii"),
                "write_plan": write_plan,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["contract_version"], "workbook-execution-result.v1")
        output = base64.b64decode(payload["workbook_base64"], validate=True)
        self.assertNotEqual(output, source_bytes)
        self.assertEqual(
            validate_workbook_execution_receipt_payload(
                payload["receipt"],
                write_plan=write_plan,
            ),
            (),
        )

    def test_receipt_validation_endpoint_matches_core(self) -> None:
        source_bytes, write_plan = execution_case()
        execution = self.client.post(
            "/api/v1/workbooks/executions",
            json={
                "contract_version": "workbook-execution-request.v1",
                "filename": "synthetic.xlsx",
                "output_filename": "completed.xlsx",
                "workbook_base64": base64.b64encode(source_bytes).decode("ascii"),
                "write_plan": write_plan,
            },
        ).json()
        response = self.client.post(
            "/api/v1/workbooks/execution-receipts/validate",
            json={"receipt": execution["receipt"], "write_plan": write_plan},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"valid": True, "issues": []})

    def test_execution_rejects_path_like_filename(self) -> None:
        source_bytes, write_plan = execution_case()
        response = self.client.post(
            "/api/v1/workbooks/executions",
            json={
                "contract_version": "workbook-execution-request.v1",
                "filename": "../synthetic.xlsx",
                "output_filename": "completed.xlsx",
                "workbook_base64": base64.b64encode(source_bytes).decode("ascii"),
                "write_plan": write_plan,
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_execution_browser_asset_is_served(self) -> None:
        response = self.client.get("/assets/execution.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("executeCopiedWorkbook", response.text)


if __name__ == "__main__":
    unittest.main()
