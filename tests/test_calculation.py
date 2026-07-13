from __future__ import annotations

import copy
import unittest

from fmr.workbook import (
    accept_calculated_workbook_bytes,
    calculation_engine_status,
    validate_workbook_calculation_acceptance_payload,
)
from tests.calculation_case import (
    populated_execution_case,
    tamper_first_generated_value,
)


def _all_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _all_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_keys(item)


class WorkbookCalculationAcceptanceTests(unittest.TestCase):
    def test_uncalculated_workbook_fails_without_recording_values(self) -> None:
        populated, write_plan, execution_receipt = populated_execution_case(
            input_value=987654321
        )
        acceptance = accept_calculated_workbook_bytes(
            populated,
            populated,
            input_filename="populated.xlsx",
            output_filename="uncalculated.xlsx",
            write_plan=write_plan,
            execution_receipt=execution_receipt,
            engine={
                "name": "external-test-engine",
                "version": "test-only",
                "adapter": "external-calculation.v1",
            },
        )

        self.assertEqual(acceptance["status"], "failed")
        self.assertGreater(
            acceptance["summary"]["missing_cached_value_count"],
            0,
        )
        self.assertEqual(
            acceptance["summary"]["input_cell_count"],
            acceptance["summary"]["populated_input_cell_count"],
        )
        self.assertFalse(acceptance["input"]["matches_execution_output_hash"])
        self.assertEqual(
            validate_workbook_calculation_acceptance_payload(
                acceptance,
                write_plan=write_plan,
                execution_receipt=execution_receipt,
            ),
            (),
        )
        self.assertTrue(
            {
                "value",
                "calculated_value",
                "cached_value",
                "before_value",
                "after_value",
            }.isdisjoint(set(_all_keys(acceptance)))
        )

    def test_calculation_output_must_preserve_generated_records(self) -> None:
        populated, write_plan, execution_receipt = populated_execution_case()
        tampered = tamper_first_generated_value(populated, write_plan)
        acceptance = accept_calculated_workbook_bytes(
            populated,
            tampered,
            input_filename="populated.xlsx",
            output_filename="tampered.xlsx",
            write_plan=write_plan,
            execution_receipt=execution_receipt,
            engine={
                "name": "external-test-engine",
                "version": "test-only",
                "adapter": "external-calculation.v1",
            },
        )

        self.assertEqual(acceptance["status"], "failed")
        self.assertTrue(
            any(
                item.startswith("output:")
                for item in acceptance["immutable_verification"][
                    "failed_record_ids"
                ]
            )
        )

    def test_acceptance_id_detects_tampering(self) -> None:
        populated, write_plan, execution_receipt = populated_execution_case()
        acceptance = accept_calculated_workbook_bytes(
            populated,
            populated,
            input_filename="populated.xlsx",
            output_filename="uncalculated.xlsx",
            write_plan=write_plan,
            execution_receipt=execution_receipt,
            engine={
                "name": "external-test-engine",
                "version": "test-only",
                "adapter": "external-calculation.v1",
            },
        )
        altered = copy.deepcopy(acceptance)
        altered["output"]["filename"] = "changed.xlsx"
        issues = validate_workbook_calculation_acceptance_payload(
            altered,
            write_plan=write_plan,
            execution_receipt=execution_receipt,
        )
        self.assertIn("acceptance_id does not match payload", issues)

    def test_missing_engine_status_is_explicit(self) -> None:
        status = calculation_engine_status("fmr-engine-that-does-not-exist")
        self.assertFalse(status["available"])
        self.assertIsNone(status["engine"])
        self.assertIn("not found", status["error"])

    def test_engine_metadata_is_closed(self) -> None:
        populated, write_plan, execution_receipt = populated_execution_case()
        with self.assertRaisesRegex(ValueError, "undeclared fields"):
            accept_calculated_workbook_bytes(
                populated,
                populated,
                input_filename="populated.xlsx",
                output_filename="uncalculated.xlsx",
                write_plan=write_plan,
                execution_receipt=execution_receipt,
                engine={
                    "name": "external-test-engine",
                    "version": "test-only",
                    "adapter": "external-calculation.v1",
                    "command": "hidden",
                },
            )


if __name__ == "__main__":
    unittest.main()
