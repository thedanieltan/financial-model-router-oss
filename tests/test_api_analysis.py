from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from fmr.api.app import MAX_WORKBOOK_MAP_REQUEST_BYTES, create_app
from fmr.types import ModelRequest
from fmr.workbook import analyse_workbook_map, inspect_workbook_bytes
from tests.xlsx_factory import financial_workbook


class WorkbookAnalysisApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())

    def test_analysis_endpoint_matches_core_exactly(self) -> None:
        workbook_map = inspect_workbook_bytes(
            financial_workbook(),
            filename="synthetic.xlsx",
        )
        request_payload = {
            "contract_version": "model-request.v1",
            "objective": "build a budget forecast",
            "role": "finance_manager",
            "available_data": [
                "balance_sheet_history",
                "revenue_drivers",
                "operating_cost_drivers",
            ],
            "workbook_capabilities": [],
            "assumptions": ["forecast_horizon"],
        }
        core = analyse_workbook_map(
            workbook_map,
            ModelRequest.from_mapping(request_payload),
        ).to_dict()
        response = self.client.post(
            "/api/v1/workbooks/analyse",
            json={
                "contract_version": "workbook-analysis-request.v1",
                "workbook_map": workbook_map.to_dict(),
                "model_request": request_payload,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), core)

    def test_invalid_workbook_map_is_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/workbooks/analyse",
            json={
                "contract_version": "workbook-analysis-request.v1",
                "workbook_map": {"contract_version": "unknown"},
                "model_request": {
                    "contract_version": "model-request.v1",
                    "objective": "build a budget forecast",
                    "role": "finance_manager",
                    "available_data": [],
                    "workbook_capabilities": [],
                    "assumptions": [],
                },
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"]["code"],
            "invalid_workbook_analysis_request",
        )

    def test_declared_oversized_analysis_request_is_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/workbooks/analyse",
            content=b"{}",
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(MAX_WORKBOOK_MAP_REQUEST_BYTES + 1),
            },
        )
        self.assertEqual(response.status_code, 413)
        self.assertFalse(response.json()["valid"])


if __name__ == "__main__":
    unittest.main()
