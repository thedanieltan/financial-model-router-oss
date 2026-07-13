from __future__ import annotations

import copy
import hashlib
import json
import unittest

from fmr.types import ModelRequest
from fmr.workbook import (
    analyse_workbook_map,
    compile_workbook_patch,
    inspect_workbook_bytes,
    plan_workbook_content,
    plan_workbook_coordinates,
    plan_workbook_realization,
    resolve_workbook_patch_targets,
    validate_workbook_realization_plan_payload,
)
from tests.xlsx_factory import financial_workbook


def budget_content_plan() -> dict:
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
    return plan_workbook_content(coordinate_plan)


def _reset_plan_id(plan: dict) -> None:
    candidate = dict(plan)
    candidate.pop("realization_plan_id", None)
    rendered = json.dumps(
        candidate,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    plan["realization_plan_id"] = f"fmrr_{hashlib.sha256(rendered).hexdigest()[:24]}"


class RealizationPlanTests(unittest.TestCase):
    def test_budget_realization_plan_binds_dependencies_and_styles(self) -> None:
        content_plan = budget_content_plan()
        plan = plan_workbook_realization(content_plan)
        self.assertEqual(plan["contract_version"], "workbook-realization-plan.v1")
        self.assertEqual(plan["expression_language"], "fmr-expression.v1")
        self.assertTrue(plan["ready_for_executor"])
        self.assertFalse(plan["execution_supported_by_this_release"])
        self.assertEqual(
            validate_workbook_realization_plan_payload(
                plan,
                content_plan=content_plan,
            ),
            (),
        )

        revenue = next(
            item
            for item in plan["operation_realizations"]
            if item["source_operation"] == "create_revenue_schedule"
        )
        formula_slot = next(
            slot
            for slot in revenue["slots"]
            if slot["identifier"] == "fmr.formula.revenue_forecast.v1"
        )
        binding = formula_slot["formula_binding"]
        self.assertEqual(binding["formula_kind"], "calculation")
        self.assertTrue(binding["expression_template"].startswith("MUL("))
        self.assertTrue(all(item["target"] for item in binding["dependencies"]))
        self.assertEqual(formula_slot["style_binding"]["semantic_type"], "currency")
        self.assertTrue(
            formula_slot["style_binding"]["role_style"]["protection"]["locked"]
        )

        input_slot = next(
            slot
            for slot in revenue["slots"]
            if slot["identifier"] == "fmr.input.growth_rate.v1"
        )
        self.assertEqual(input_slot["style_binding"]["semantic_type"], "percentage")
        self.assertFalse(
            input_slot["style_binding"]["role_style"]["protection"]["locked"]
        )

    def test_forecast_copy_formulas_use_period_context(self) -> None:
        plan = plan_workbook_realization(budget_content_plan())
        forecast = next(
            item
            for item in plan["operation_realizations"]
            if item["source_operation"] == "add_forecast_periods"
        )
        formula_slots = [
            slot for slot in forecast["slots"] if slot["formula_binding"] is not None
        ]
        self.assertGreater(len(formula_slots), 1)
        for slot in formula_slots:
            binding = slot["formula_binding"]
            self.assertEqual(binding["formula_kind"], "copy_rule")
            self.assertEqual(binding["dependencies"][0]["binding_type"], "period_context")
            self.assertEqual(slot["style_binding"]["semantic_type"], "preserve_source")

    def test_validator_detects_tampering(self) -> None:
        content_plan = budget_content_plan()
        plan = plan_workbook_realization(content_plan)
        tampered = copy.deepcopy(plan)
        first_styled = next(
            slot
            for operation in tampered["operation_realizations"]
            for slot in operation["slots"]
            if slot.get("style_binding")
        )
        first_styled["style_binding"]["role_style"]["font"]["family"] = "Other"
        issues = validate_workbook_realization_plan_payload(
            tampered,
            content_plan=content_plan,
        )
        self.assertIn("realization_plan_id does not match payload", issues)
        self.assertIn("realization plan does not match deterministic recomputation", issues)

    def test_validator_rejects_nested_undeclared_fields_after_id_recalculation(self) -> None:
        plan = plan_workbook_realization(budget_content_plan())
        tampered = copy.deepcopy(plan)
        first_slot = next(
            slot
            for operation in tampered["operation_realizations"]
            for slot in operation["slots"]
        )
        first_slot["undeclared"] = True
        _reset_plan_id(tampered)
        issues = validate_workbook_realization_plan_payload(tampered)
        self.assertTrue(
            any("contains undeclared fields" in issue for issue in issues),
            issues,
        )


if __name__ == "__main__":
    unittest.main()
