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
    plan_workbook_realization,
    resolve_workbook_patch_targets,
)
from tests.xlsx_factory import financial_workbook


def _content_plan() -> dict:
    workbook_map = inspect_workbook_bytes(financial_workbook(), filename="synthetic.xlsx")
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
    return plan_workbook_content(coordinate_plan)


class RealizationPlanApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())

    def test_formula_and_style_registries_are_discoverable(self) -> None:
        formula = self.client.get("/api/v1/workbook-formula-specs")
        style = self.client.get("/api/v1/workbook-style-specs")
        self.assertEqual(formula.status_code, 200)
        self.assertEqual(style.status_code, 200)
        self.assertEqual(
            formula.json()["contract_version"],
            "workbook-formula-spec-registry.v1",
        )
        self.assertEqual(
            style.json()["contract_version"],
            "workbook-style-spec-registry.v1",
        )

    def test_realization_endpoint_matches_core(self) -> None:
        content_plan = _content_plan()
        expected = plan_workbook_realization(content_plan)
        response = self.client.post(
            "/api/v1/workbooks/realization-plans",
            json={
                "contract_version": "workbook-realization-plan-request.v1",
                "content_plan": content_plan,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)

    def test_realization_validation_recomputes_source(self) -> None:
        content_plan = _content_plan()
        realization = plan_workbook_realization(content_plan)
        valid = self.client.post(
            "/api/v1/workbooks/realization-plans/validate",
            json={
                "realization_plan": realization,
                "content_plan": content_plan,
            },
        )
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json(), {"valid": True, "issues": []})

        tampered = copy.deepcopy(realization)
        first_formula = next(
            slot
            for operation in tampered["operation_realizations"]
            for slot in operation["slots"]
            if slot.get("formula_binding")
        )
        first_formula["formula_binding"]["expression_template"] += " "
        invalid = self.client.post(
            "/api/v1/workbooks/realization-plans/validate",
            json={
                "realization_plan": tampered,
                "content_plan": content_plan,
            },
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(invalid.json()["valid"])
        self.assertIn(
            "realization plan does not match deterministic recomputation",
            invalid.json()["issues"],
        )

    def test_realization_request_rejects_extra_fields(self) -> None:
        response = self.client.post(
            "/api/v1/workbooks/realization-plans",
            json={
                "contract_version": "workbook-realization-plan-request.v1",
                "content_plan": _content_plan(),
                "unexpected": True,
            },
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
