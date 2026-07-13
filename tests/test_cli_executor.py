from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fmr.dispatch import main
from tests.test_executor import execution_case


class WorkbookExecutorCliTests(unittest.TestCase):
    def test_execute_and_validate_receipt_commands(self) -> None:
        source_bytes, write_plan = execution_case()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.xlsx"
            output = root / "completed.xlsx"
            write_plan_path = root / "write-plan.json"
            receipt_path = root / "receipt.json"
            source.write_bytes(source_bytes)
            write_plan_path.write_text(json.dumps(write_plan), encoding="utf-8")

            self.assertEqual(
                main([
                    "execute-writes",
                    str(source),
                    str(write_plan_path),
                    "--output",
                    str(output),
                    "--receipt",
                    str(receipt_path),
                ]),
                0,
            )
            self.assertTrue(output.is_file())
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["contract_version"], "workbook-execution-receipt.v1")

            self.assertEqual(
                main([
                    "validate-execution-receipt",
                    str(receipt_path),
                    "--write-plan",
                    str(write_plan_path),
                ]),
                0,
            )

    def test_execute_refuses_existing_output(self) -> None:
        source_bytes, write_plan = execution_case()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.xlsx"
            output = root / "completed.xlsx"
            write_plan_path = root / "write-plan.json"
            receipt_path = root / "receipt.json"
            source.write_bytes(source_bytes)
            output.write_bytes(b"existing")
            write_plan_path.write_text(json.dumps(write_plan), encoding="utf-8")

            self.assertEqual(
                main([
                    "execute-writes",
                    str(source),
                    str(write_plan_path),
                    "--output",
                    str(output),
                    "--receipt",
                    str(receipt_path),
                ]),
                2,
            )
            self.assertEqual(output.read_bytes(), b"existing")
            self.assertFalse(receipt_path.exists())


if __name__ == "__main__":
    unittest.main()
