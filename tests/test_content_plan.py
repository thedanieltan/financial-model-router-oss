from __future__ import annotations

import copy
import unittest
from dataclasses import replace
from typing import Any

from fmr.types import ModelRequest
from fmr.workbook import (
    WorkbookMap,
    analyse_workbook_map,
    compile_workbook_patch,
    inspect_workbook_bytes,
    plan_workbook_content,
    plan_workbook_coordinates,
    resolve_workbook_patch_targets,
    validate_workbook_content_plan_payload,
)
from tests.xlsx_factory import financial_workbook


def _keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            found.add(str(key).lower())
            found.update(_keys(nested))
    elif isinstance(value, list):
        for item in value:
            found.update(_keys(item))
    return found


def budget_request() -> ModelRequest:
    return ModelRequest(
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


def dcf_request() -> ModelRequest:
    return ModelRequest(
        objective="value an operating company using a DCF",
        role="finance_manager",
        available_data=(
            "income_statement_history",
            "balance_sheet_history",
            "cash_flow_history",
            "revenue_drivers",
            "capital_expenditure_schedule",
            "working_capital_schedule",
            "net_debt",
        ),
        workbook_capabilities=("historical_periods", "assumptions_section"),
        assumptions=(
            "forecast_horizon",
            "tax_rate",
            "discount_rate",
            "terminal_value_assumption",
        ),
    )


def coordinate_plan(request: ModelRequest, *, periods: int = 5) -> dict:
    workbook_map = inspect_workbook_bytes(
        financial_workbook(),
        filename="synthetic.xlsx",
    )
    analysis = analyse_workbook_map(workbook_map, request)
    patch = compile_workbook_patch(analysis).to_dict()
    resolution = resolve_workbook_patch_targets(analysis, patch).to_dict()
    return plan_workbook_coordinates(
        analysis,
        patch,
        resolution,
        forecast_period_count=periods,
    )


class ContentPlanTests(unittest.TestCase):
    def test_budget_content_plan_is_deterministic_and_symbolic(self) -> None:
        coordinates = coordinate_plan(budget_request(), periods=5)
        plan = plan_workbook_content(coordinates)

        self.assertEqual(plan["contract_version"], "workbook-content-plan.v1")
        self.assertTrue(plan["ready_for_executor"])
        self.assertFalse(plan["execution_supported_by_this_release"])
        self.assertEqual(
            validate_workbook_content_plan_payload(
                plan,
                coordinate_plan=coordinates,
            ),
            (),
        )

        by_operation = {
            item["source_operation"]: item for item in plan["operation_contents"]
        }
        assumptions = by_operation["create_assumptions_section"]
        self.assertEqual(assumptions["status"], "satisfied_existing")
        self.assertEqual(assumptions["slots"], [])

        revenue = by_operation["create_revenue_schedule"]
        self.assertEqual(revenue["status"], "planned_content")
        title = next(item for item in revenue["slots"] if item["slot_id"] == "a1_title")
        self.assertEqual(title["coordinate"], "A1:J1")
        output = next(
            item
            for item in revenue["slots"]
            if item["content_kind"] == "formula_identifier"
        )
        self.assertTrue(output["identifier"].startswith("fmr.formula."))
        self.assertNotIn("formula", output)

        forecast = by_operation["add_forecast_periods"]
        self.assertEqual(forecast["status"], "planned_content")
        header_slots = [
            item for item in forecast["slots"] if item["content_kind"] == "period_header"
        ]
        self.assertEqual(len(header_slots), 10)
        for forbidden in (
            "cell_write",
            "formula",
            "value",
            "number_format",
            "macro",
            "vba",
            "workbook_bytes",
        ):
            self.assertNotIn(forbidden, _keys(plan))

    def test_reference_only_content_has_no_coordinates(self) -> None:
        coordinates = coordinate_plan(dcf_request())
        plan = plan_workbook_content(coordinates)
        links = next(
            item
            for item in plan["operation_contents"]
            if item["source_operation"] == "link_financial_statements"
        )
        self.assertEqual(links["status"], "reference_only")
        self.assertEqual(len(links["slots"]), 3)
        self.assertTrue(all(slot["coordinate"] is None for slot in links["slots"]))
        self.assertTrue(
            all(slot["content_kind"] == "reference_identifier" for slot in links["slots"])
        )

    def test_validator_detects_tampering(self) -> None:
        coordinates = coordinate_plan(budget_request())
        plan = plan_workbook_content(coordinates)
        tampered = copy.deepcopy(plan)
        revenue = next(
            item
            for item in tampered["operation_contents"]
            if item["source_operation"] == "create_revenue_schedule"
        )
        revenue["slots"][0]["coordinate"] = "A1:I1"
        issues = validate_workbook_content_plan_payload(
            tampered,
            coordinate_plan=coordinates,
        )
        self.assertIn("content_plan_id does not match payload", issues)
        self.assertIn("content plan does not match deterministic recomputation", issues)

    def test_blocked_coordinate_plan_propagates(self) -> None:
        workbook_map = inspect_workbook_bytes(
            financial_workbook(),
            filename="synthetic.xlsx",
        )
        constrained_sheets = tuple(
            replace(sheet, used_range="A1:XFD5")
            if sheet.name == "Income Statement"
            else sheet
            for sheet in workbook_map.sheets
        )
        constrained_map = WorkbookMap(
            source_filename=workbook_map.source_filename,
            source_sha256=workbook_map.source_sha256,
            source_size_bytes=workbook_map.source_size_bytes,
            sheet_count=workbook_map.sheet_count,
            defined_names=workbook_map.defined_names,
            external_links_detected=workbook_map.external_links_detected,
            sheets=constrained_sheets,
            findings=workbook_map.findings,
            limitations=workbook_map.limitations,
        )
        analysis = analyse_workbook_map(constrained_map, budget_request())
        patch = compile_workbook_patch(analysis).to_dict()
        resolution = resolve_workbook_patch_targets(analysis, patch).to_dict()
        coordinates = plan_workbook_coordinates(
            analysis,
            patch,
            resolution,
            forecast_period_count=5,
        )
        plan = plan_workbook_content(coordinates)
        self.assertFalse(plan["ready_for_executor"])
        self.assertTrue(
            any(item.startswith("coordinate_plan:") for item in plan["blockers"])
        )


if __name__ == "__main__":
    unittest.main()
