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
)
from tests.xlsx_factory import financial_workbook


class TargetResolutionCliTests(unittest.TestCase):
    def test_registry_resolution_and_validation_commands(self) -> None:
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

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "analysis.json"
            patch_path = root / "patch.json"
            registry_path = root / "operation-specs.json"
            resolution_path = root / "target-resolution.json"
            analysis_path.write_text(
                json.dumps(analysis.to_dict()),
                encoding="utf-8",
            )
            patch_path.write_text(json.dumps(patch), encoding="utf-8")

            self.assertEqual(
                main(["operation-specs", "--output", str(registry_path)]),
                0,
            )
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertEqual(
                registry["contract_version"],
                "workbook-operation-spec-registry.v1",
            )

            self.assertEqual(
                main([
                    "resolve-targets",
                    str(analysis_path),
                    str(patch_path),
                    "--output",
                    str(resolution_path),
                ]),
                0,
            )
            resolution = json.loads(
                resolution_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                resolution["contract_version"],
                "workbook-target-resolution.v1",
            )
            self.assertTrue(resolution["ready_for_executor"])

            self.assertEqual(
                main([
                    "validate-target-resolution",
                    str(resolution_path),
                    "--analysis",
                    str(analysis_path),
                    "--patch",
                    str(patch_path),
                ]),
                0,
            )


if __name__ == "__main__":
    unittest.main()
