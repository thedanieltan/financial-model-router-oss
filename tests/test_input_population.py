from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from fmr.workbook import (
    compile_workbook_input_set_from_csv,
    populate_workbook_inputs_bytes,
    populate_workbook_inputs_file,
    validate_input_population_calculation_link,
    validate_workbook_input_population_receipt_payload,
    validate_workbook_input_set_payload,
)
from fmr.workbook.executor import _cells
from tests.input_population_case import (
    input_csv_bytes,
    input_population_case,
    reserved_records,
)


class WorkbookInputPopulationTests(unittest.TestCase):
    def test_csv_compiles_deterministically_and_covers_reserved_inputs(self) -> None:
        executed, write_plan, execution_receipt, input_set, csv_bytes = (
            input_population_case()
        )
        del executed
        self.assertEqual(
            validate_workbook_input_set_payload(
                input_set,
                write_plan=write_plan,
                execution_receipt=execution_receipt,
            ),
            (),
        )
        repeated = compile_workbook_input_set_from_csv(
            csv_bytes,
            source_name="inputs.csv",
            write_plan=write_plan,
            execution_receipt=execution_receipt,
        )
        self.assertEqual(repeated, input_set)
        self.assertEqual(
            [item["record_id"] for item in input_set["bindings"]],
            [item["record_id"] for item in reserved_records(write_plan)],
        )

    def test_population_writes_only_reserved_inputs_and_emits_value_free_receipt(self) -> None:
        executed, write_plan, execution_receipt, input_set, _ = (
            input_population_case(value=7)
        )
        source_hash = hashlib.sha256(executed).hexdigest()
        result = populate_workbook_inputs_bytes(
            executed,
            filename="executed.xlsx",
            output_filename="populated.xlsx",
            write_plan=write_plan,
            execution_receipt=execution_receipt,
            input_set=input_set,
        )
        self.assertEqual(hashlib.sha256(executed).hexdigest(), source_hash)
        self.assertNotEqual(result.output_bytes, executed)
        self.assertEqual(
            validate_workbook_input_population_receipt_payload(
                result.receipt,
                input_set=input_set,
                write_plan=write_plan,
                execution_receipt=execution_receipt,
            ),
            (),
        )
        receipt = result.receipt
        self.assertEqual(receipt["status"], "completed")
        self.assertEqual(
            receipt["source"]["sha256"], execution_receipt["output"]["sha256"]
        )
        self.assertEqual(receipt["verification"]["failed_record_ids"], [])
        self.assertEqual(
            receipt["verification"]["populated_record_count"],
            len(reserved_records(write_plan)),
        )
        forbidden = {
            "value",
            "values",
            "input_value",
            "before_value",
            "after_value",
            "cell_value",
        }
        self.assertTrue(forbidden.isdisjoint(set(_keys(receipt))))
        rendered = json.dumps(receipt, sort_keys=True)
        self.assertNotIn('"values"', rendered)

        workbook = load_workbook(BytesIO(result.output_bytes), data_only=False)
        try:
            bindings = {item["record_id"]: item for item in input_set["bindings"]}
            for record in reserved_records(write_plan):
                actual = [
                    cell.value
                    for cell in _cells(
                        workbook[record["sheet_name"]], record["coordinate"]
                    )
                ]
                self.assertEqual(actual, bindings[record["record_id"]]["values"])
        finally:
            workbook.close()

    def test_population_rejects_wrong_execution_output_hash(self) -> None:
        executed, write_plan, execution_receipt, input_set, _ = input_population_case()
        with self.assertRaisesRegex(ValueError, "hash does not match"):
            populate_workbook_inputs_bytes(
                executed + b"x",
                filename="executed.xlsx",
                output_filename="populated.xlsx",
                write_plan=write_plan,
                execution_receipt=execution_receipt,
                input_set=input_set,
            )

    def test_csv_rejects_incomplete_unknown_and_non_finite_values(self) -> None:
        _, write_plan, execution_receipt, _, csv_bytes = input_population_case()
        lines = csv_bytes.decode("utf-8").splitlines()
        with self.assertRaisesRegex(
            ValueError,
            "missing reserved input record|cell_index|values count does not match reserved range",
        ):
            compile_workbook_input_set_from_csv(
                ("\n".join(lines[:-1]) + "\n").encode("utf-8"),
                source_name="incomplete.csv",
                write_plan=write_plan,
                execution_receipt=execution_receipt,
            )

        unknown = (
            csv_bytes.decode("utf-8")
            + "fmrw_999999,1,number,3,synthetic:unknown\n"
        ).encode("utf-8")
        with self.assertRaisesRegex(ValueError, "unknown or non-input"):
            compile_workbook_input_set_from_csv(
                unknown,
                source_name="unknown.csv",
                write_plan=write_plan,
                execution_receipt=execution_receipt,
            )

        non_finite = input_csv_bytes(write_plan).decode("utf-8").replace(
            ",7,", ",nan,", 1
        )
        with self.assertRaisesRegex(ValueError, "finite"):
            compile_workbook_input_set_from_csv(
                non_finite.encode("utf-8"),
                source_name="non-finite.csv",
                write_plan=write_plan,
                execution_receipt=execution_receipt,
            )

    def test_input_set_validator_rejects_type_and_shape_tampering(self) -> None:
        _, write_plan, execution_receipt, input_set, _ = input_population_case()
        altered = copy.deepcopy(input_set)
        altered["bindings"][0]["value_type"] = "boolean"
        self.assertTrue(
            any(
                "does not match value_type" in issue
                for issue in validate_workbook_input_set_payload(
                    altered,
                    write_plan=write_plan,
                    execution_receipt=execution_receipt,
                )
            )
        )

        altered = copy.deepcopy(input_set)
        altered["bindings"][0]["values"].append(7)
        self.assertTrue(
            any(
                "count does not match" in issue
                for issue in validate_workbook_input_set_payload(
                    altered,
                    write_plan=write_plan,
                    execution_receipt=execution_receipt,
                )
            )
        )

    def test_file_population_never_overwrites_source_or_existing_output(self) -> None:
        executed, write_plan, execution_receipt, input_set, _ = input_population_case()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "executed.xlsx"
            output = root / "populated.xlsx"
            source.write_bytes(executed)
            receipt = populate_workbook_inputs_file(
                source,
                output_path=output,
                write_plan=write_plan,
                execution_receipt=execution_receipt,
                input_set=input_set,
            )
            self.assertTrue(output.is_file())
            self.assertEqual(
                receipt["output"]["sha256"],
                hashlib.sha256(output.read_bytes()).hexdigest(),
            )
            with self.assertRaisesRegex(ValueError, "already exists"):
                populate_workbook_inputs_file(
                    source,
                    output_path=output,
                    write_plan=write_plan,
                    execution_receipt=execution_receipt,
                    input_set=input_set,
                )
            with self.assertRaisesRegex(ValueError, "must differ"):
                populate_workbook_inputs_file(
                    source,
                    output_path=source,
                    write_plan=write_plan,
                    execution_receipt=execution_receipt,
                    input_set=input_set,
                )

    def test_population_to_calculation_link_is_hash_pinned(self) -> None:
        executed, write_plan, execution_receipt, input_set, _ = input_population_case()
        result = populate_workbook_inputs_bytes(
            executed,
            filename="executed.xlsx",
            output_filename="populated.xlsx",
            write_plan=write_plan,
            execution_receipt=execution_receipt,
            input_set=input_set,
        )
        acceptance = {
            "contract_version": "workbook-calculation-acceptance.v1",
            "write_plan_id": result.receipt["write_plan_id"],
            "write_plan_sha256": result.receipt["write_plan_sha256"],
            "execution_id": result.receipt["execution_id"],
            "execution_receipt_sha256": result.receipt[
                "execution_receipt_sha256"
            ],
            "input": dict(result.receipt["output"]),
        }
        self.assertEqual(
            validate_input_population_calculation_link(result.receipt, acceptance),
            (),
        )
        acceptance["input"]["sha256"] = "0" * 64
        self.assertIn(
            "calculation input hash does not match population output",
            validate_input_population_calculation_link(result.receipt, acceptance),
        )


def _keys(value):  # type: ignore[no-untyped-def]
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


if __name__ == "__main__":
    unittest.main()
