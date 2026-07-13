from __future__ import annotations

import copy
import unittest

from fastapi.testclient import TestClient

from fmr.api.composed import create_app
from fmr.workbook import compile_workbook_write_plan
from tests.test_write_plan import budget_realization_plan, write_context


class WorkbookWritePlanApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())

    def test_write_plan_endpoint_matches_core(self) -> None:
        realization = budget_realization_plan()
        context = write_context(realization)
        expected = compile_workbook_write_plan(realization, context)
        response = self.client.post(
            "/api/v1/workbooks/write-plans",
            json={
                "contract_version": "workbook-write-plan-request.v1",
                "realization_plan": realization,
                "write_context": context,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)

    def test_write_plan_validation_recomputes_sources(self) -> None:
        realization = budget_realization_plan()
        context = write_context(realization)
        write_plan = compile_workbook_write_plan(realization, context)
        valid = self.client.post(
            "/api/v1/workbooks/write-plans/validate",
            json={
                "write_plan": write_plan,
                "realization_plan": realization,
                "write_context": context,
            },
        )
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json(), {"valid": True, "issues": []})

        tampered = copy.deepcopy(write_plan)
        first_formula = next(
            record
            for phase in tampered["phases"]
            for record in phase["records"]
            if record["write_kind"] == "write_formula"
        )
        first_formula["payload"]["formula"] = "=0"
        invalid = self.client.post(
            "/api/v1/workbooks/write-plans/validate",
            json={
                "write_plan": tampered,
                "realization_plan": realization,
                "write_context": context,
            },
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(invalid.json()["valid"])
        self.assertIn(
            "write plan does not match deterministic recomputation",
            invalid.json()["issues"],
        )

    def test_write_plan_request_rejects_extra_fields(self) -> None:
        realization = budget_realization_plan()
        response = self.client.post(
            "/api/v1/workbooks/write-plans",
            json={
                "contract_version": "workbook-write-plan-request.v1",
                "realization_plan": realization,
                "write_context": write_context(realization),
                "unexpected": True,
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_browser_modules_are_served(self) -> None:
        self.assertEqual(self.client.get("/assets/realization.js").status_code, 200)
        self.assertEqual(self.client.get("/assets/write_plan.js").status_code, 200)


if __name__ == "__main__":
    unittest.main()
