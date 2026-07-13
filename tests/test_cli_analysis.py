from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fmr.cli import main
from tests.xlsx_factory import financial_workbook


class WorkbookAnalysisCliTests(unittest.TestCase):
    def test_analyse_workbook_writes_self_contained_result(self) -> None:
        request = {
            "contract_version": "model-request.v1",
            "objective": "build a budget forecast",
            "role": "finance_manager",
            "available_data": [
                "balance_sheet_history",
                "revenue_drivers",
                "operating_cost_drivers"
            ],
            "workbook_capabilities": [],
            "assumptions": ["forecast_horizon"]
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workbook = root / "synthetic.xlsx"
            request_path = root / "request.json"
            output = root / "analysis.json"
            workbook.write_bytes(financial_workbook())
            request_path.write_text(json.dumps(request), encoding="utf-8")

            exit_code = main([
                "analyse-workbook",
                str(workbook),
                str(request_path),
                "--output",
                str(output),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["contract_version"], "workbook-analysis.v1")
            self.assertTrue(payload["recommendation"]["readiness"]["ready"])
            self.assertIn(
                "income_statement_history",
                payload["derived_evidence"]["available_data"],
            )


if __name__ == "__main__":
    unittest.main()
