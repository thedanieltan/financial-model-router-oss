from __future__ import annotations

import json
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator

from fmr.providers.native_xlsx.workbook.formula_plan import (
    plan_monthly_fpa_formula_file,
    plan_monthly_fpa_formula_map,
    validate_workbook_formula_plan_payload,
)
from fmr.providers.native_xlsx.workbook.semantic import map_workbook_semantics_bytes
from tests.xlsx_factory import build_xlsx


def monthly_formula_workbook(*, include_unresolved: bool = False) -> bytes:
    cells = {
        "A1": "Management P&L - SGD in thousands",
        "B2": "Jan-26 Actual",
        "C2": "Feb-26 Actual",
        "D2": "Mar-26 Forecast",
        "E2": "Apr-26 Forecast",
        "A3": "Revenue",
        "B3": 100,
        "C3": {"formula": "B3*1.05", "value": 105},
        "A4": "Operating Costs",
        "B4": 60,
        "C4": {"formula": "B4*1.02", "value": 61.2},
    }
    if include_unresolved:
        cells.update({"A5": "Cash", "B5": 40, "C5": 42})
    return build_xlsx([{"name": "Monthly P&L", "cells": cells}])


class WorkbookFormulaPlanTests(unittest.TestCase):
    def test_plans_formula_extension_from_existing_lineage_without_raw_formula_text(self) -> None:
        semantic = map_workbook_semantics_bytes(monthly_formula_workbook(), filename="monthly-fpa.xlsx")
        payload = plan_monthly_fpa_formula_map(semantic)
        self.assertTrue(payload["ready_for_write"])
        self.assertEqual(payload["target_sheet"], "Monthly P&L")
        self.assertEqual(
            [(record["target"]["cell"], record["bindings"][0]["source_type"], record["bindings"][0]["source"]["cell"]) for record in payload["records"]],
            [("D3", "workbook_formula_cell", "C3"), ("E3", "planned_formula_cell", "D3"), ("D4", "workbook_formula_cell", "C4"), ("E4", "planned_formula_cell", "D4")],
        )
        self.assertTrue(all(record["formula_specification"]["identifier"] == "fmr.formula.forecast_column_copy.v1" for record in payload["records"]))
        rendered = json.dumps(payload, sort_keys=True)
        self.assertNotIn('"formula":', rendered)
        self.assertNotIn('"value":', rendered)
        self.assertEqual(validate_workbook_formula_plan_payload(payload, semantic_map=semantic), ())

    def test_fails_closed_when_forecast_row_has_no_preceding_formula(self) -> None:
        semantic = map_workbook_semantics_bytes(monthly_formula_workbook(include_unresolved=True), filename="monthly-fpa.xlsx")
        payload = plan_monthly_fpa_formula_map(semantic)
        self.assertFalse(payload["ready_for_write"])
        self.assertIn("unresolved_forecast_formula_targets", payload["blockers"])
        cash = [item for item in payload["unresolved"] if item["metric"] == "cash"]
        self.assertEqual(cash[0]["target_cell"], "D5")
        self.assertEqual(cash[0]["reason"], "preceding_period_is_not_formula")

    def test_is_deterministic_read_only_and_schema_valid(self) -> None:
        data = monthly_formula_workbook()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "monthly-fpa.xlsx"
            path.write_bytes(data)
            before = path.read_bytes()
            first = plan_monthly_fpa_formula_file(path)
            second = plan_monthly_fpa_formula_file(path)
            after = path.read_bytes()
        self.assertEqual(before, after)
        self.assertEqual(first, second)
        schema = json.loads(files("fmr.providers.native_xlsx.contracts").joinpath("workbook-formula-plan.v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(first)

    def test_provider_and_compatibility_contracts_are_identical(self) -> None:
        provider = files("fmr.providers.native_xlsx.contracts").joinpath("workbook-formula-plan.v1.schema.json").read_bytes()
        compatibility = files("fmr.contracts").joinpath("workbook-formula-plan.v1.schema.json").read_bytes()
        self.assertEqual(provider, compatibility)


if __name__ == "__main__":
    unittest.main()
