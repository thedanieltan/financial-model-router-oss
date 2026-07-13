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
    plan_workbook_coordinates,
    resolve_workbook_patch_targets,
)
from tests.xlsx_factory import financial_workbook


class ContentPlanCliTests(unittest.TestCase):
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
        coordinate_plan = plan_workbook_coordinates(
            analysis,
            patch,
            resolution,
            forecast_period_count=5,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinate_path = root / "coordinate-plan.json"
            registry_path = root / "content-specs.json"
            content_path = root / "content-plan.json"
            coordinate_path.write_text(
                json.dumps(coordinate_plan),
                encoding="utf-8",
            )

            self.assertEqual(
                main(["content-specs", "--output", str(registry_path)]),
                0,
            )
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertEqual(
                registry["contract_version"],
                "workbook-content-spec-registry.v1",
            )

            self.assertEqual(
                main([
                    "plan-content",
                    str(coordinate_path),
                    "--output",
                    str(content_path),
                ]),
                0,
            )
            content_plan = json.loads(content_path.read_text(encoding="utf-8"))
            self.assertEqual(
                content_plan["contract_version"],
                "workbook-content-plan.v1",
            )
            self.assertTrue(content_plan["ready_for_executor"])

            self.assertEqual(
                main([
                    "validate-content-plan",
                    str(content_path),
                    "--coordinate-plan",
                    str(coordinate_path),
                ]),
                0,
            )


if __name__ == "__main__":
    unittest.main()
