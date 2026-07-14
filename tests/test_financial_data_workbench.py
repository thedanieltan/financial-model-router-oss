from __future__ import annotations

import unittest
from importlib.resources import files


class FinancialDataWorkbenchTests(unittest.TestCase):
    def test_financial_data_controls_and_boundaries_are_visible(self) -> None:
        index = files("fmr.web").joinpath("index.html").read_text(encoding="utf-8")
        script = files("fmr.web").joinpath("financial_data.js").read_text(
            encoding="utf-8"
        )
        for element_id in (
            'id="financial-data-file"',
            'id="import-financial-data-button"',
            'id="map-financial-data-button"',
            'id="financial-mapping-rules-editor"',
            'id="financial-binding-profile-editor"',
            'id="plan-financial-bindings-button"',
            'id="compile-financial-input-set-button"',
        ):
            self.assertIn(element_id, index)
        self.assertIn('/assets/financial_data.js', index)
        self.assertIn('Exact mappings and explicit bindings only', index)
        self.assertIn('/api/v1/financial-data/packages/from-csv', script)
        self.assertIn('/api/v1/financial-data/mappings', script)
        self.assertIn('/api/v1/financial-data/binding-plans', script)
        self.assertIn('/api/v1/financial-data/input-sets', script)
        self.assertIn('currentFinancialBindingPlan.ready_for_input_set', script)
        self.assertNotIn('localStorage', script)
        self.assertNotIn('sessionStorage', script)


if __name__ == "__main__":
    unittest.main()
