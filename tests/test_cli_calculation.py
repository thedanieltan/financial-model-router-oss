from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fmr.dispatch import main
from tests.calculation_case import populated_execution_case


class WorkbookCalculationCliTests(unittest.TestCase):
    def test_accept_external_output_and_validate_receipt(self) -> None:
        populated, write_plan, execution_receipt = populated_execution_case()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "populated.xlsx"
            calculated_path = root / "uncalculated.xlsx"
            write_plan_path = root / "write-plan.json"
            execution_path = root / "execution.json"
            acceptance_path = root / "acceptance.json"
            input_path.write_bytes(populated)
            calculated_path.write_bytes(populated)
            write_plan_path.write_text(json.dumps(write_plan), encoding="utf-8")
            execution_path.write_text(
                json.dumps(execution_receipt), encoding="utf-8"
            )

            self.assertEqual(
                main([
                    "accept-calculated-output",
                    str(input_path),
                    str(calculated_path),
                    str(write_plan_path),
                    str(execution_path),
                    "--receipt",
                    str(acceptance_path),
                    "--engine-name",
                    "external-test-engine",
                    "--engine-version",
                    "test-only",
                ]),
                2,
            )
            acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
            self.assertEqual(acceptance["status"], "failed")
            self.assertGreater(
                acceptance["summary"]["missing_cached_value_count"],
                0,
            )

            self.assertEqual(
                main([
                    "validate-calculation-acceptance",
                    str(acceptance_path),
                    "--write-plan",
                    str(write_plan_path),
                    "--execution-receipt",
                    str(execution_path),
                ]),
                0,
            )

    def test_calculation_engine_status_reports_missing_binary(self) -> None:
        self.assertEqual(
            main([
                "calculation-engine-status",
                "--engine",
                "fmr-engine-that-does-not-exist",
            ]),
            2,
        )


if __name__ == "__main__":
    unittest.main()
