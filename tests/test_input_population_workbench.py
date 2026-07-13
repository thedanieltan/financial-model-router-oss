from __future__ import annotations

import unittest
from importlib.resources import files


class WorkbookInputPopulationWorkbenchTests(unittest.TestCase):
    def test_governed_input_controls_and_boundary_are_visible(self) -> None:
        index = files("fmr.web").joinpath("index.html").read_text(encoding="utf-8")
        script = files("fmr.web").joinpath("input_population.js").read_text(
            encoding="utf-8"
        )
        calculation = files("fmr.web").joinpath("calculation.js").read_text(
            encoding="utf-8"
        )
        for element_id in (
            'id="input-csv-file"',
            'id="compile-input-csv-button"',
            'id="input-set-editor"',
            'id="populate-inputs-button"',
            'id="input-population-status"',
        ):
            self.assertIn(element_id, index)
        self.assertIn('/assets/input_population.js', index)
        self.assertIn('selected source is never overwritten', index)
        self.assertIn('input or calculated values are not written to receipts', index)
        self.assertIn('/api/v1/workbooks/input-sets/from-csv', script)
        self.assertIn('/api/v1/workbooks/input-populations', script)
        self.assertIn('currentPopulatedWorkbookBase64', script)
        self.assertIn('currentInputPopulationReceipt', calculation)
        self.assertIn('validate-calculation-link', calculation)
        for content in (script, calculation):
            self.assertNotIn('localStorage', content)
            self.assertNotIn('sessionStorage', content)


if __name__ == "__main__":
    unittest.main()
