from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fmr.entrypoint import main
from tests.input_population_case import input_population_case


class WorkbookInputPopulationCliTests(unittest.TestCase):
    def test_compile_populate_validate_and_link_commands(self) -> None:
        executed, write_plan, execution_receipt, _, csv_bytes = input_population_case()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workbook_path = root / "executed.xlsx"
            csv_path = root / "inputs.csv"
            write_plan_path = root / "write-plan.json"
            execution_path = root / "execution-receipt.json"
            input_set_path = root / "input-set.json"
            output_path = root / "populated.xlsx"
            receipt_path = root / "population-receipt.json"
            acceptance_path = root / "calculation-acceptance.json"

            workbook_path.write_bytes(executed)
            csv_path.write_bytes(csv_bytes)
            write_plan_path.write_text(json.dumps(write_plan), encoding="utf-8")
            execution_path.write_text(
                json.dumps(execution_receipt), encoding="utf-8"
            )

            self.assertEqual(
                main(
                    [
                        "compile-input-set-csv",
                        str(csv_path),
                        str(write_plan_path),
                        str(execution_path),
                        "--output",
                        str(input_set_path),
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "validate-input-set",
                        str(input_set_path),
                        "--write-plan",
                        str(write_plan_path),
                        "--execution-receipt",
                        str(execution_path),
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "populate-inputs",
                        str(workbook_path),
                        str(input_set_path),
                        str(write_plan_path),
                        str(execution_path),
                        "--output",
                        str(output_path),
                        "--receipt",
                        str(receipt_path),
                    ]
                ),
                0,
            )
            self.assertTrue(output_path.is_file())
            self.assertEqual(
                main(
                    [
                        "validate-input-population-receipt",
                        str(receipt_path),
                        "--input-set",
                        str(input_set_path),
                        "--write-plan",
                        str(write_plan_path),
                        "--execution-receipt",
                        str(execution_path),
                    ]
                ),
                0,
            )

            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            acceptance = {
                "contract_version": "workbook-calculation-acceptance.v1",
                "write_plan_id": receipt["write_plan_id"],
                "write_plan_sha256": receipt["write_plan_sha256"],
                "execution_id": receipt["execution_id"],
                "execution_receipt_sha256": receipt[
                    "execution_receipt_sha256"
                ],
                "input": receipt["output"],
            }
            acceptance_path.write_text(json.dumps(acceptance), encoding="utf-8")
            self.assertEqual(
                main(
                    [
                        "validate-input-calculation-link",
                        str(receipt_path),
                        str(acceptance_path),
                    ]
                ),
                0,
            )

    def test_population_command_refuses_existing_output(self) -> None:
        executed, write_plan, execution_receipt, input_set, _ = (
            input_population_case()
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workbook_path = root / "executed.xlsx"
            output_path = root / "populated.xlsx"
            input_set_path = root / "input-set.json"
            write_plan_path = root / "write-plan.json"
            execution_path = root / "execution.json"
            receipt_path = root / "receipt.json"
            workbook_path.write_bytes(executed)
            output_path.write_bytes(b"existing")
            input_set_path.write_text(json.dumps(input_set), encoding="utf-8")
            write_plan_path.write_text(json.dumps(write_plan), encoding="utf-8")
            execution_path.write_text(
                json.dumps(execution_receipt), encoding="utf-8"
            )
            self.assertEqual(
                main(
                    [
                        "populate-inputs",
                        str(workbook_path),
                        str(input_set_path),
                        str(write_plan_path),
                        str(execution_path),
                        "--output",
                        str(output_path),
                        "--receipt",
                        str(receipt_path),
                    ]
                ),
                2,
            )
            self.assertEqual(output_path.read_bytes(), b"existing")
            self.assertFalse(receipt_path.exists())


if __name__ == "__main__":
    unittest.main()
