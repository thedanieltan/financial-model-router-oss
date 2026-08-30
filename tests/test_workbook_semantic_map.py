from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator

from fmr.providers.native_xlsx.workbook import map_workbook_semantics, map_workbook_semantics_bytes
from fmr.providers.native_xlsx.workbook.classify import classify_metric_label, classify_period_label
from tests.xlsx_factory import build_xlsx, financial_workbook


class WorkbookSemanticMapTests(unittest.TestCase):
    def test_maps_metric_rows_period_cells_and_formula_lineage_without_values(self) -> None:
        payload = map_workbook_semantics_bytes(
            financial_workbook(include_chart=False),
            filename="finance.xlsx",
        )
        self.assertEqual(payload["contract_version"], "workbook-semantic-map.v1")
        income = payload["sheets"][0]
        self.assertEqual(income["role"]["value"], "income_statement")
        self.assertEqual(
            [(item["coordinate"], item["label"], item["classification"]["value"]) for item in income["period_columns"]],
            [("B2", "2024", "unspecified"), ("C2", "2025", "unspecified"), ("D2", "2026E", "forecast")],
        )
        revenue = next(item for item in income["metric_rows"] if item["metric"]["value"] == "revenue")
        self.assertEqual(revenue["label_cell"], "A3")
        self.assertEqual([item["coordinate"] for item in revenue["period_cells"]], ["B3", "C3", "D3"])
        self.assertEqual(revenue["period_cells"][-1]["cell_kind"], "formula")
        formula = next(item for item in income["formula_dependencies"] if item["formula_cell"] == "D3")
        self.assertEqual(formula["references"], [{"sheet": None, "range": "C3", "external": False}])
        self.assertNotIn("formula", formula)
        for row in income["metric_rows"]:
            for period_cell in row["period_cells"]:
                self.assertEqual(set(period_cell), {"coordinate", "period_label", "period_kind", "cell_kind"})

    def test_maps_monthly_quarterly_driver_tabs_currency_scale_and_cross_sheet_dependencies(self) -> None:
        data = build_xlsx([
            {
                "name": "Monthly P&L",
                "cells": {
                    "A1": "Management P&L - SGD in thousands",
                    "B2": "Jan-26",
                    "C2": "Feb-26",
                    "D2": "Mar-26",
                    "A3": "Revenue",
                    "B3": 100,
                    "C3": 105,
                    "D3": {"formula": "'Sales Drivers'!D4*'Sales Drivers'!D5", "value": 110},
                    "A4": "Payroll",
                    "B4": 20,
                    "C4": 22,
                    "D4": {"formula": "'HC Plan'!D3*'HC Plan'!D4", "value": 24},
                },
            },
            {
                "name": "HC Plan",
                "cells": {
                    "A1": "Headcount Plan",
                    "B2": "Jan-26",
                    "C2": "Feb-26",
                    "D2": "Mar-26",
                    "A3": "Headcount",
                    "B3": 10,
                    "C3": 11,
                    "D3": 12,
                    "A4": "Salary Cost",
                    "B4": 2,
                    "C4": 2,
                    "D4": 2,
                },
            },
            {
                "name": "Sales Drivers",
                "cells": {
                    "A1": "Revenue Drivers",
                    "B2": "Q1 2026",
                    "C2": "Q2 2026",
                    "D2": "Q3 2026",
                    "A4": "Customers",
                    "B4": 50,
                    "C4": 55,
                    "D4": 60,
                    "A5": "Average Selling Price",
                    "B5": 2,
                    "C5": 2,
                    "D5": 2,
                },
            },
            {
                "name": "Budget FY26",
                "cells": {
                    "A1": "Budget FY26",
                    "B2": "2026 Budget",
                    "C2": "2027F",
                    "A3": "Revenue",
                    "B3": 1200,
                    "C3": 1300,
                    "A4": "Operating Costs",
                    "B4": 800,
                    "C4": 850,
                },
            },
        ])
        first = map_workbook_semantics_bytes(data, filename="operator-model.xlsx")
        second = map_workbook_semantics_bytes(data, filename="operator-model.xlsx")
        self.assertEqual(first, second)
        pnl = first["sheets"][0]
        self.assertEqual(pnl["role"]["value"], "income_statement")
        self.assertEqual(pnl["currency_evidence"][0]["value"], "SGD")
        self.assertEqual(pnl["scale_evidence"][0]["value"], "thousands")
        hc = first["sheets"][1]
        self.assertEqual(hc["role"]["value"], "headcount_schedule")
        self.assertIn("headcount", {item["metric"]["value"] for item in hc["metric_rows"]})
        sales = first["sheets"][2]
        self.assertEqual(sales["role"]["value"], "revenue_schedule")
        budget = first["sheets"][3]
        self.assertEqual(budget["role"]["value"], "budget_forecast")
        dependencies = first["cross_sheet_dependencies"]
        self.assertIn({"from_sheet": "Monthly P&L", "formula_cell": "D3", "to_sheet": "Sales Drivers", "target_range": "D4", "external": False}, dependencies)
        self.assertIn({"from_sheet": "Monthly P&L", "formula_cell": "D4", "to_sheet": "HC Plan", "target_range": "D3", "external": False}, dependencies)

    def test_mapping_is_read_only_and_schema_valid(self) -> None:
        data = financial_workbook(include_chart=False)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "finance.xlsx"
            path.write_bytes(data)
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            payload = map_workbook_semantics(path)
            after = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(before, after)
        self.assertEqual(payload["source"]["sha256"], before)
        schema = json.loads(
            files("fmr.providers.native_xlsx.contracts")
            .joinpath("workbook-semantic-map.v1.schema.json")
            .read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(payload)

    def test_provider_and_compatibility_contracts_are_identical(self) -> None:
        provider = files("fmr.providers.native_xlsx.contracts").joinpath("workbook-semantic-map.v1.schema.json").read_bytes()
        compatibility = files("fmr.contracts").joinpath("workbook-semantic-map.v1.schema.json").read_bytes()
        self.assertEqual(provider, compatibility)

    def test_period_and_metric_classification_is_conservative(self) -> None:
        self.assertEqual(classify_period_label("Jan-26").value, "unspecified")
        self.assertEqual(classify_period_label("Q2 2026").value, "unspecified")
        self.assertEqual(classify_period_label("2027F").value, "forecast")
        self.assertEqual(classify_metric_label("Average Selling Price").value, "price")
        self.assertEqual(classify_metric_label("A completely custom management note").value, "unknown")


if __name__ == "__main__":
    unittest.main()
