from __future__ import annotations

import copy
import unittest

from fastapi.testclient import TestClient

from fmr.api.app import create_app
from fmr.types import ModelRequest
from fmr.workbook import (
    analyse_workbook_map,
    compile_workbook_patch,
    inspect_workbook_bytes,
)
from tests.xlsx_factory import financial_workbook


class WorkbookPatchApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())
        workbook_map = inspect_workbook_bytes(
            financial_workbook(),
            filename="synthetic.xlsx",
        )
        request = ModelRequest(
            objective="build a budget forecast",
            role="finance_manager",
            available_data=(
                "balance_sheet_history",
                "revenue_drivers",
                "operating_cost_drivers",
            ),
            workbook_capabilities=(),
            assumptions=("forecast_horizon",),
        )
        cls.analysis = analyse_workbook_map(workbook_map, request)
        cls.patch = compile_workbook_patch(cls.analysis).to_dict()

    def test_compile_endpoint_matches_core_exactly(self) -> None:
        response = self.client.post(
            "/api/v1/workbooks/patches",
            json=self.analysis.to_dict(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.patch)

    def test_patch_validation_endpoint_detects_tampering(self) -> None:
        valid = self.client.post(
            "/api/v1/workbooks/patches/validate",
            json=self.patch,
        )
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json(), {"valid": True, "issues": []})

        tampered = copy.deepcopy(self.patch)
        tampered["source"]["sha256"] = "0" * 64
        invalid = self.client.post(
            "/api/v1/workbooks/patches/validate",
            json=tampered,
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(invalid.json()["valid"])
        self.assertIn("patch_id does not match payload", invalid.json()["issues"])

    def test_receipt_validation_can_reference_patch(self) -> None:
        receipt = {
            "contract_version": "workbook-patch-receipt.v1",
            "patch_id": self.patch["patch_id"],
            "source_sha256": self.patch["source"]["sha256"],
            "output_sha256": "b" * 64,
            "status": "applied",
            "operation_receipts": [
                {
                    "operation_id": operation["operation_id"],
                    "status": "applied",
                    "before_state_sha256": "c" * 64,
                    "after_state_sha256": "d" * 64,
                    "rollback_state_sha256": None,
                    "affected_parts": ["xl/workbook.xml"],
                }
                for operation in self.patch["operations"]
            ],
            "validations": [
                {
                    "check": "output_reopens_as_xlsx",
                    "passed": True,
                    "message": "output archive reopened",
                }
            ],
        }
        response = self.client.post(
            "/api/v1/workbooks/patch-receipts/validate",
            json={"receipt": receipt, "patch": self.patch},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"valid": True, "issues": []})

    def test_workbench_exposes_patch_compilation(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Compile patch", response.text)
        self.assertIn("Patch execution is not included", response.text)


if __name__ == "__main__":
    unittest.main()
