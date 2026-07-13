from __future__ import annotations

import unittest
from importlib.resources import files


class WorkbookExecutorWorkbenchTests(unittest.TestCase):
    def test_execution_action_and_boundary_are_visible(self) -> None:
        index = files("fmr.web").joinpath("index.html").read_text(encoding="utf-8")
        script = files("fmr.web").joinpath("execution.js").read_text(encoding="utf-8")
        self.assertIn('id="execute-workbook-button"', index)
        self.assertIn('/assets/execution.js', index)
        self.assertIn('Patch execution is not included', index)
        self.assertIn('selected source is never overwritten', index)
        self.assertIn('/api/v1/workbooks/executions', script)
        self.assertIn('downloadBase64Workbook', script)
        self.assertIn('The selected source file was not modified', script)
        self.assertNotIn('localStorage', script)
        self.assertNotIn('sessionStorage', script)


if __name__ == "__main__":
    unittest.main()
