from __future__ import annotations

import copy
import unittest

from fmr.workbook import (
    compile_workbook_write_plan,
    validate_workbook_write_plan_payload,
)
from tests.test_write_plan import budget_realization_plan, write_context


class WorkbookWritePlanValidationTests(unittest.TestCase):
    def test_standalone_validation_rejects_undeclared_record_payload_fields(self) -> None:
        realization = budget_realization_plan()
        context = write_context(realization)
        plan = compile_workbook_write_plan(realization, context)
        tampered = copy.deepcopy(plan)
        first_record = next(
            record
            for phase in tampered["phases"]
            for record in phase["records"]
            if record["write_kind"] == "write_formula"
        )
        first_record["payload"]["workbook_bytes"] = "not-allowed"
        issues = validate_workbook_write_plan_payload(tampered)
        self.assertTrue(any("undeclared fields" in item for item in issues))

    def test_standalone_validation_rejects_external_formula_links(self) -> None:
        realization = budget_realization_plan()
        context = write_context(realization)
        plan = compile_workbook_write_plan(realization, context)
        tampered = copy.deepcopy(plan)
        first_record = next(
            record
            for phase in tampered["phases"]
            for record in phase["records"]
            if record["write_kind"] == "write_formula"
        )
        first_record["payload"]["formula"] = "='[other.xlsx]Sheet1'!A1"
        issues = validate_workbook_write_plan_payload(tampered)
        self.assertTrue(any("forbidden reference syntax" in item for item in issues))


if __name__ == "__main__":
    unittest.main()
