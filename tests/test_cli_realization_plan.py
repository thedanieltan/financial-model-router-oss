from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fmr.cli import main
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


class RealizationPlanCliTests(unittest.TestCase):
    def test_registries_plan_and_validation_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content_path = root / "content-plan.json"
            formula_path = root / "formula-specs.json"
            style_path = root / "style-specs.json"
            realization_path = root / "realization-plan.json"
            content_path.write_text(json.dumps(_content_plan()), encoding="utf-8")

            self.assertEqual(main(["formula-specs", "--output", str(formula_path)]), 0)
            self.assertEqual(main(["style-specs", "--output", str(style_path)]), 0)
            self.assertEqual(
                main([
                    "plan-realization",
                    str(content_path),
                    "--output",
                    str(realization_path),
                ]),
                0,
            )
            self.assertEqual(
                main([
                    "validate-realization-plan",
                    str(realization_path),
                    "--content-plan",
                    str(content_path),
                ]),
                0,
            )

            formula_registry = json.loads(formula_path.read_text(encoding="utf-8"))
            style_registry = json.loads(style_path.read_text(encoding="utf-8"))
            realization = json.loads(realization_path.read_text(encoding="utf-8"))
            self.assertEqual(
                formula_registry["contract_version"],
                "workbook-formula-spec-registry.v1",
            )
            self.assertEqual(
                style_registry["contract_version"],
                "workbook-style-spec-registry.v1",
            )
            self.assertEqual(
                realization["contract_version"],
                "workbook-realization-plan.v1",
            )
            self.assertTrue(realization["ready_for_executor"])


if __name__ == "__main__":
    unittest.main()
