from __future__ import annotations

import unittest
from importlib.resources import files


class WorkbookWritePlanWorkbenchTests(unittest.TestCase):
    def test_write_plan_controls_and_script_are_packaged(self) -> None:
        index = files("fmr.web").joinpath("index.html").read_text(encoding="utf-8")
        script = files("fmr.web").joinpath("write_plan.js").read_text(encoding="utf-8")
        self.assertIn('id="write-context-editor"', index)
        self.assertIn('id="plan-writes-button"', index)
        self.assertIn('/assets/write_plan.js', index)
        self.assertIn('/api/v1/workbooks/write-plans', script)
        self.assertIn('workbook-write-context.v1', script)
        self.assertIn('Synthetic write bindings were generated for local testing', script)
        self.assertNotIn('workbook_bytes', script)


if __name__ == "__main__":
    unittest.main()
