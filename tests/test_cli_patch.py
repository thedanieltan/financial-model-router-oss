from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from fmr.cli import main
from tests.xlsx_factory import financial_workbook


class WorkbookPatchCliTests(unittest.TestCase):
    def test_compile_and_validate_patch(self) -> None:
        request = {
            "contract_version": "model-request.v1",
            "objective": "build a budget forecast",
            "role": "finance_manager",
            "available_data": [
                "balance_sheet_history",
                "revenue_drivers",
                "operating_cost_drivers",
            ],
            "workbook_capabilities": [],
            "assumptions": ["forecast_horizon"],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workbook = root / "synthetic.xlsx"
            request_path = root / "request.json"
            analysis_path = root / "analysis.json"
            patch_path = root / "patch.json"
            workbook.write_bytes(financial_workbook())
            request_path.write_text(json.dumps(request), encoding="utf-8")

            self.assertEqual(
                main([
                    "analyse-workbook",
                    str(workbook),
                    str(request_path),
                    "--output",
                    str(analysis_path),
                ]),
                0,
            )
            self.assertEqual(
                main([
                    "compile-patch",
                    str(analysis_path),
                    "--output",
                    str(patch_path),
                ]),
                0,
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["validate-patch", str(patch_path)]), 0)

            patch = json.loads(patch_path.read_text(encoding="utf-8"))
            self.assertEqual(patch["contract_version"], "workbook-patch.v1")
            self.assertTrue(patch["ready_for_executor"])
            self.assertFalse(patch["execution_supported_by_this_release"])

    def test_invalid_patch_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "patch.json"
            path.write_text(json.dumps({"contract_version": "workbook-patch.v1"}), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["validate-patch", str(path)]), 2)


if __name__ == "__main__":
    unittest.main()
