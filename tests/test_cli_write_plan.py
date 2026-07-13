from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fmr.dispatch import main
from tests.test_write_plan import budget_realization_plan, write_context


class WorkbookWritePlanCliTests(unittest.TestCase):
    def test_plan_and_validate_write_plan_commands(self) -> None:
        realization = budget_realization_plan()
        context = write_context(realization)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            realization_path = root / "realization.json"
            context_path = root / "write-context.json"
            write_plan_path = root / "write-plan.json"
            realization_path.write_text(json.dumps(realization), encoding="utf-8")
            context_path.write_text(json.dumps(context), encoding="utf-8")

            self.assertEqual(
                main([
                    "plan-writes",
                    str(realization_path),
                    str(context_path),
                    "--output",
                    str(write_plan_path),
                ]),
                0,
            )
            payload = json.loads(write_plan_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["contract_version"], "workbook-write-plan.v1")
            self.assertTrue(payload["ready_for_executor"])

            self.assertEqual(
                main([
                    "validate-write-plan",
                    str(write_plan_path),
                    "--realization-plan",
                    str(realization_path),
                    "--write-context",
                    str(context_path),
                ]),
                0,
            )


if __name__ == "__main__":
    unittest.main()
