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
    plan_workbook_content,
    plan_workbook_coordinates,
    resolve_workbook_patch_targets,
)
from tests.xlsx_factory import financial_workbook


def _coordinate_plan() -> dict:
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
    return plan_workbook_coordinates(
        analysis,
        patch,
        resolution,
        forecast_period_count=5,
    )


class ContentPlanApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())

    def test_content_registry_is_discoverable(self) -> None:
        response = self.client.get("/api/v1/workbook-content-specs")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["contract_version"],
            "workbook-content-spec-registry.v1",
        )
        self.assertGreater(len(payload["specifications"]), 10)

    def test_content_plan_endpoint_matches_core(self) -> None:
        coordinate_plan = _coordinate_plan()
        expected = plan_workbook_content(coordinate_plan)
        response = self.client.post(
            "/api/v1/workbooks/content-plans",
            json={
                "contract_version": "workbook-content-plan-request.v1",
                "coordinate_plan": coordinate_plan,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)

    def test_content_plan_validation_recomputes_source_contract(self) -> None:
        coordinate_plan = _coordinate_plan()
        content_plan = plan_workbook_content(coordinate_plan)
        valid = self.client.post(
            "/api/v1/workbooks/content-plans/validate",
            json={
                "content_plan": content_plan,
                "coordinate_plan": coordinate_plan,
            },
        )
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json(), {"valid": True, "issues": []})

        tampered = copy.deepcopy(content_plan)
        first_with_slots = next(
            item for item in tampered["operation_contents"] if item["slots"]
        )
        first_with_slots["slots"][0]["format_role"] = "output"
        invalid = self.client.post(
            "/api/v1/workbooks/content-plans/validate",
            json={
                "content_plan": tampered,
                "coordinate_plan": coordinate_plan,
            },
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(invalid.json()["valid"])
        self.assertIn(
            "content plan does not match deterministic recomputation",
            invalid.json()["issues"],
        )

    def test_content_plan_request_rejects_extra_fields(self) -> None:
        coordinate_plan = _coordinate_plan()
        response = self.client.post(
            "/api/v1/workbooks/content-plans",
            json={
                "contract_version": "workbook-content-plan-request.v1",
                "coordinate_plan": coordinate_plan,
                "unexpected": True,
            },
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
