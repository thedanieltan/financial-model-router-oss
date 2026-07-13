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
    resolve_workbook_patch_targets,
)
from tests.xlsx_factory import financial_workbook


def _contracts() -> tuple[dict, dict, dict]:
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
    analysis = analyse_workbook_map(workbook_map, request)
    patch = compile_workbook_patch(analysis).to_dict()
    resolution = resolve_workbook_patch_targets(analysis, patch).to_dict()
    return analysis.to_dict(), patch, resolution


class TargetResolutionApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())

    def test_operation_registry_is_discoverable(self) -> None:
        response = self.client.get("/api/v1/workbook-operation-specs")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["contract_version"],
            "workbook-operation-spec-registry.v1",
        )
        self.assertGreater(len(payload["specifications"]), 10)

    def test_resolution_endpoint_matches_core(self) -> None:
        analysis, patch, expected = _contracts()
        response = self.client.post(
            "/api/v1/workbooks/target-resolutions",
            json={
                "contract_version": "workbook-target-resolution-request.v1",
                "workbook_analysis": analysis,
                "workbook_patch": patch,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)

    def test_resolution_validation_recomputes_source_contracts(self) -> None:
        analysis, patch, resolution = _contracts()
        valid = self.client.post(
            "/api/v1/workbooks/target-resolutions/validate",
            json={
                "target_resolution": resolution,
                "workbook_analysis": analysis,
                "workbook_patch": patch,
            },
        )
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json(), {"valid": True, "issues": []})

        tampered = copy.deepcopy(resolution)
        tampered["resolutions"][0]["status"] = "resolved_new"
        invalid = self.client.post(
            "/api/v1/workbooks/target-resolutions/validate",
            json={
                "target_resolution": tampered,
                "workbook_analysis": analysis,
                "workbook_patch": patch,
            },
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(invalid.json()["valid"])
        self.assertIn(
            "target resolution does not match deterministic recomputation",
            invalid.json()["issues"],
        )

    def test_resolution_rejects_mismatched_patch(self) -> None:
        analysis, patch, _ = _contracts()
        patch["source"]["filename"] = "other.xlsx"
        response = self.client.post(
            "/api/v1/workbooks/target-resolutions",
            json={
                "contract_version": "workbook-target-resolution-request.v1",
                "workbook_analysis": analysis,
                "workbook_patch": patch,
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"]["code"],
            "invalid_target_resolution_request",
        )


if __name__ == "__main__":
    unittest.main()
