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
    plan_workbook_coordinates,
    resolve_workbook_patch_targets,
)
from tests.xlsx_factory import financial_workbook


def _contracts() -> tuple[dict, dict, dict, dict]:
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
    coordinate_plan = plan_workbook_coordinates(
        analysis,
        patch,
        resolution,
        forecast_period_count=5,
    )
    return analysis.to_dict(), patch, resolution, coordinate_plan


class CoordinatePlanApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())

    def test_coordinate_registry_is_discoverable(self) -> None:
        response = self.client.get("/api/v1/workbook-coordinate-rules")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["contract_version"],
            "workbook-coordinate-rule-registry.v1",
        )
        self.assertGreater(len(payload["rules"]), 10)

    def test_coordinate_plan_endpoint_matches_core(self) -> None:
        analysis, patch, resolution, expected = _contracts()
        response = self.client.post(
            "/api/v1/workbooks/coordinate-plans",
            json={
                "contract_version": "workbook-coordinate-plan-request.v1",
                "analysis": analysis,
                "patch": patch,
                "target_resolution": resolution,
                "layout_parameters": {"forecast_period_count": 5},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)

    def test_coordinate_plan_validation_recomputes_context(self) -> None:
        analysis, patch, resolution, coordinate_plan = _contracts()
        valid = self.client.post(
            "/api/v1/workbooks/coordinate-plans/validate",
            json={
                "coordinate_plan": coordinate_plan,
                "analysis": analysis,
                "patch": patch,
                "target_resolution": resolution,
                "layout_parameters": {"forecast_period_count": 5},
            },
        )
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json(), {"valid": True, "issues": []})

        tampered = copy.deepcopy(coordinate_plan)
        tampered["layout_parameters"]["forecast_period_count"] = 6
        invalid = self.client.post(
            "/api/v1/workbooks/coordinate-plans/validate",
            json={
                "coordinate_plan": tampered,
                "analysis": analysis,
                "patch": patch,
                "target_resolution": resolution,
                "layout_parameters": {"forecast_period_count": 5},
            },
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(invalid.json()["valid"])
        self.assertIn(
            "coordinate plan does not match deterministic recomputation",
            invalid.json()["issues"],
        )

    def test_coordinate_plan_rejects_invalid_period_count(self) -> None:
        analysis, patch, resolution, _ = _contracts()
        response = self.client.post(
            "/api/v1/workbooks/coordinate-plans",
            json={
                "contract_version": "workbook-coordinate-plan-request.v1",
                "analysis": analysis,
                "patch": patch,
                "target_resolution": resolution,
                "layout_parameters": {"forecast_period_count": 0},
            },
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
