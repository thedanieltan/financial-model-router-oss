from __future__ import annotations

import copy
import unittest

from fmr.types import ModelRequest
from fmr.workbook import (
    analyse_workbook_map,
    compile_workbook_patch,
    compile_workbook_write_plan,
    inspect_workbook_bytes,
    plan_workbook_content,
    plan_workbook_coordinates,
    plan_workbook_realization,
    resolve_workbook_patch_targets,
    validate_workbook_write_context_payload,
    validate_workbook_write_plan_payload,
)
from tests.xlsx_factory import financial_workbook


def budget_realization_plan() -> dict:
    workbook_map = inspect_workbook_bytes(
        financial_workbook(),
        filename="synthetic.xlsx",
    )
    request = ModelRequest(
        objective="build a budget forecast",
        role="finance_manager",
        available_data=(
            "balance_sheet_history",
            "revenue_drivers",
            "operating_cost_drivers",
        ),
        workbook_capabilities=(),
        assumptions=("forecast_horizon",),
    )
    analysis = analyse_workbook_map(workbook_map, request)
    patch = compile_workbook_patch(analysis).to_dict()
    resolution = resolve_workbook_patch_targets(analysis, patch).to_dict()
    coordinate_plan = plan_workbook_coordinates(
        analysis,
        patch,
        resolution,
        forecast_period_count=5,
    )
    content_plan = plan_workbook_content(coordinate_plan)
    return plan_workbook_realization(content_plan)


def write_context(realization_plan: dict) -> dict:
    bindings: dict[str, dict] = {}
    for operation in realization_plan["operation_realizations"]:
        for slot in operation["slots"]:
            formula = slot.get("formula_binding")
            if not isinstance(formula, dict):
                continue
            for dependency in formula["dependencies"]:
                if dependency["binding_type"] in {"content_slot", "period_context"}:
                    continue
                bindings[dependency["identifier"]] = {
                    "binding_type": "constant",
                    "value": True if dependency["binding_type"] == "validation_context" else 1,
                }
    return {
        "contract_version": "workbook-write-context.v1",
        "period_labels": [
            "2024A",
            "2025A",
            "2026E",
            "2027E",
            "2028E",
            "2029E",
            "2030E",
            "2031E",
            "2032E",
            "2033E",
            "2034E",
            "2035E",
        ],
        "bindings": bindings,
    }


class WorkbookWritePlanTests(unittest.TestCase):
    def test_write_plan_compiles_explicit_ordered_records(self) -> None:
        realization = budget_realization_plan()
        context = write_context(realization)
        plan = compile_workbook_write_plan(realization, context)

        self.assertEqual(plan["contract_version"], "workbook-write-plan.v1")
        self.assertEqual(plan["formula_language"], "excel-a1.v1")
        self.assertTrue(plan["ready_for_executor"])
        self.assertFalse(plan["execution_supported_by_this_release"])
        self.assertEqual(
            validate_workbook_write_plan_payload(
                plan,
                realization_plan=realization,
                write_context=context,
            ),
            (),
        )
        self.assertEqual([item["phase"] for item in plan["phases"]], [10, 20, 30, 40])

        records = [record for phase in plan["phases"] for record in phase["records"]]
        self.assertEqual(
            [record["sequence"] for record in records],
            list(range(1, len(records) + 1)),
        )
        self.assertEqual(plan["write_record_count"], len(records))
        formulas = [
            record["payload"]["formula"]
            for record in records
            if record["write_kind"] == "write_formula"
        ]
        self.assertTrue(formulas)
        self.assertTrue(all(item.startswith("=") for item in formulas))
        self.assertTrue(all("{{" not in item and "}}" not in item for item in formulas))
        self.assertTrue(any("PRODUCT(" in item for item in formulas))
        self.assertTrue(any(record["write_kind"] == "reserve_input" for record in records))
        self.assertTrue(any(record["write_kind"] == "apply_style" for record in records))

    def test_missing_external_bindings_block_without_guessing(self) -> None:
        realization = budget_realization_plan()
        context = write_context(realization)
        context["bindings"] = {}
        plan = compile_workbook_write_plan(realization, context)
        self.assertFalse(plan["ready_for_executor"])
        self.assertTrue(any("binding_missing:" in item for item in plan["blockers"]))

    def test_context_rejects_formula_strings_and_undeclared_fields(self) -> None:
        payload = {
            "contract_version": "workbook-write-context.v1",
            "period_labels": ["2026E"],
            "bindings": {
                "fmr.source.ebit.v1": {
                    "binding_type": "constant",
                    "value": "=A1",
                    "formula": "=A1",
                }
            },
        }
        issues = validate_workbook_write_context_payload(payload)
        self.assertTrue(any("undeclared fields" in item for item in issues))
        self.assertTrue(any("numeric or boolean" in item for item in issues))

    def test_validator_detects_formula_tampering(self) -> None:
        realization = budget_realization_plan()
        context = write_context(realization)
        plan = compile_workbook_write_plan(realization, context)
        tampered = copy.deepcopy(plan)
        formula_record = next(
            record
            for phase in tampered["phases"]
            for record in phase["records"]
            if record["write_kind"] == "write_formula"
        )
        formula_record["payload"]["formula"] = "=1"
        issues = validate_workbook_write_plan_payload(
            tampered,
            realization_plan=realization,
            write_context=context,
        )
        self.assertIn("write_plan_id does not match payload", issues)
        self.assertIn("write plan does not match deterministic recomputation", issues)


if __name__ == "__main__":
    unittest.main()
