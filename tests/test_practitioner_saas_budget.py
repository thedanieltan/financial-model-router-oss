from __future__ import annotations

import importlib.util
import unittest

from fmr.practitioner.saas_budget import (
    build_saas_budget_workbook_from_payload,
    validate_saas_budget_workbook_bytes,
)


@unittest.skipIf(importlib.util.find_spec("openpyxl") is None, "openpyxl not installed")
class PractitionerSaasBudgetTest(unittest.TestCase):
    def test_generates_formula_driven_practitioner_workbook(self) -> None:
        payload = {
            "company_name": "Test SaaS Co",
            "currency": "SGD",
            "forecast_months": 12,
            "opening_arr": 1_200_000,
            "monthly_new_arr": 50_000,
            "monthly_expansion_arr": 15_000,
            "monthly_contraction_arr": 5_000,
            "monthly_churned_arr": 10_000,
            "gross_margin_rate": 0.8,
            "sales_marketing_monthly": 80_000,
            "rnd_monthly": 90_000,
            "ga_monthly": 50_000,
            "starting_cash": 1_500_000,
            "headcount": 25,
            "average_salary_per_head_monthly": 9_000,
        }
        workbook = build_saas_budget_workbook_from_payload(payload)
        validation = validate_saas_budget_workbook_bytes(workbook)

        self.assertTrue(validation["valid"], validation["issues"])
        self.assertEqual(validation["sheet_count"], 8)
        self.assertGreaterEqual(validation["formula_count"], 30)

    def test_rejects_invalid_gross_margin(self) -> None:
        with self.assertRaisesRegex(ValueError, "gross_margin_rate"):
            build_saas_budget_workbook_from_payload({"gross_margin_rate": 1.2})

    def test_rejects_invalid_horizon(self) -> None:
        with self.assertRaisesRegex(ValueError, "forecast_months"):
            build_saas_budget_workbook_from_payload({"forecast_months": 0})


if __name__ == "__main__":
    unittest.main()
