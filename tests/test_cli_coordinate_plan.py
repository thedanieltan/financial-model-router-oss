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
    resolve_workbook_patch_targets,
)
from tests.xlsx_factory import financial_workbook


class CoordinatePlanCliTests(unittest.TestCase):
    def test_registry_plan_and_validation_commands(self) -> None:
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

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            patch_path = root / "patch.json"
            resolution_path = root / "resolution.json"
            registry_path = root / "coordinate-rules.json"
            plan_path = root / "coordinate-plan.json"
            analysis_path.write_text(json.dumps(analysis.to_dict()), encoding="utf-8")
            patch_path.write_text(json.dumps(patch), encoding="utf-8")
            resolution_path.write_text(json.dumps(resolution), encoding="utf-8")

            self.assertEqual(
                main(["coordinate-rules", "--output", str(registry_path)]),
                0,
            )
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertEqual(
                registry["contract_version"],
                "workbook-coordinate-rule-registry.v1",
            )

            self.assertEqual(
                main([
                    "plan-coordinates",
                    str(analysis_path),
                    str(patch_path),
                    str(resolution_path),
                    "--forecast-period-count",
                    "5",
                    "--output",
                    str(plan_path),
                ]),
                0,
            )
            coordinate_plan = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(
                coordinate_plan["contract_version"],
                "workbook-coordinate-plan.v1",
            )
            self.assertTrue(coordinate_plan["ready_for_executor"])

            self.assertEqual(
                main([
                    "validate-coordinate-plan",
                    str(plan_path),
                    "--analysis",
                    str(analysis_path),
                    "--patch",
                    str(patch_path),
                    "--resolution",
                    str(resolution_path),
                    "--forecast-period-count",
                    "5",
                ]),
                0,
            )


if __name__ == "__main__":
    unittest.main()
