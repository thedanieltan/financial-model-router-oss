from __future__ import annotations

import unittest
from importlib.resources import files


class WorkbookCalculationWorkbenchTests(unittest.TestCase):
    def test_calculation_action_and_boundary_are_visible(self) -> None:
        index = files("fmr.web").joinpath("index.html").read_text(encoding="utf-8")
        script = files("fmr.web").joinpath("calculation.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('id="calculation-file"', index)
        self.assertIn('id="calculate-output-button"', index)
        self.assertIn('/assets/calculation.js', index)
        self.assertIn('calculated values are not written to receipts', index)
        self.assertIn('/api/v1/calculation-engine', script)
        self.assertIn('/api/v1/workbooks/calculations', script)
        self.assertIn('No workbook was downloaded', script)
        self.assertNotIn('localStorage', script)
        self.assertNotIn('sessionStorage', script)


if __name__ == "__main__":
    unittest.main()
