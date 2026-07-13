from __future__ import annotations

import unittest
from importlib.resources import files


class RealizationWorkbenchTests(unittest.TestCase):
    def test_workbench_loads_realization_module_and_preserves_boundary(self) -> None:
        root = files("fmr.web")
        index = root.joinpath("index.html").read_text(encoding="utf-8")
        script = root.joinpath("realization.js").read_text(encoding="utf-8")

        self.assertIn('id="plan-realization-button"', index)
        self.assertIn('src="/assets/realization.js"', index)
        self.assertIn("Patch execution is not included", index)
        self.assertIn("/api/v1/workbooks/realization-plans", script)
        self.assertIn("workbook-realization-plan-request.v1", script)
        self.assertIn("workbook-realization-plan.v1", script)
        self.assertNotIn("innerHTML", script)


if __name__ == "__main__":
    unittest.main()
