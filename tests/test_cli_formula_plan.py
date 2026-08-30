from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from fmr.entrypoint import main
from tests.test_workbook_formula_plan import monthly_formula_workbook


class FormulaPlanCliTests(unittest.TestCase):
    def test_formula_plan_cli_emits_dry_run_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workbook = Path(directory) / "monthly-fpa.xlsx"
            workbook.write_bytes(monthly_formula_workbook())
            output = StringIO()
            with redirect_stdout(output):
                code = main(["formula-plan", str(workbook)])
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["contract_version"], "workbook-formula-plan.v1")
        self.assertTrue(payload["ready_for_write"])


if __name__ == "__main__":
    unittest.main()
