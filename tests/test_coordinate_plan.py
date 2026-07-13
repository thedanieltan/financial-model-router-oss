from __future__ import annotations

import copy
import unittest
from dataclasses import replace

from fmr.types import ModelRequest
from fmr.workbook import (
    COORDINATE_RULES,
    OPERATION_SPECS,
    WorkbookMap,
    analyse_workbook_map,
    compile_workbook_patch,
    coordinate_rule_registry_payload,
    inspect_workbook_bytes,
    plan_workbook_coordinates,
    resolve_workbook_patch_targets,
    validate_workbook_coordinate_plan_payload,
)
from tests.xlsx_factory import financial_workbook


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


def contracts(request: ModelRequest) -> tuple:
    workbook_map = inspect_workbook_bytes(
        financial_workbook(),
        filename="synthetic.xlsx",
    )
    analysis = analyse_workbook_map(workbook_map, request)
    patch = compile_workbook_patch(analysis).to_dict()
    resolution = resolve_workbook_patch_targets(analysis, patch).to_dict()
    return workbook_map, analysis, patch, resolution


class CoordinatePlanTests(unittest.TestCase):
    def test_coordinate_registry_covers_every_operation(self) -> None:
        self.assertEqual(set(COORDINATE_RULES), set(OPERATION_SPECS))
        registry = coordinate_rule_registry_payload()
        self.assertEqual(
            registry["contract_version"],
            "workbook-coordinate-rule-registry.v1",
        )
        self.assertEqual(len(registry["registry_sha256"]), 64)
        self.assertEqual(len(registry["rules"]), len(OPERATION_SPECS))

    def test_budget_coordinate_plan_is_deterministic_and_collision_free(self) -> None:
        _, analysis, patch, resolution = contracts(budget_request())
        plan = plan_workbook_coordinates(
            analysis,
            patch,
            resolution,
            forecast_period_count=5,
        )
        self.assertEqual(plan["contract_version"], "workbook-coordinate-plan.v1")
        self.assertTrue(plan["ready_for_executor"])
        self.assertFalse(plan["execution_supported_by_this_release"])
        self.assertEqual(
            validate_workbook_coordinate_plan_payload(
                plan,
                analysis=analysis,
                patch=patch,
                target_resolution=resolution,
                forecast_period_count=5,
            ),
            (),
        )

        by_operation = {
            item["source_operation"]: item for item in plan["operation_plans"]
        }
        self.assertEqual(
            by_operation["create_assumptions_section"]["status"],
            "satisfied_existing",
        )
        forecast_ranges = {
            item["sheet_name"]: item["range"]
            for item in by_operation["add_forecast_periods"]["allocations"]
        }
        self.assertEqual(forecast_ranges["Income Statement"], "E1:I5")
        self.assertEqual(forecast_ranges["Balance Sheet"], "D1:H5")
        self.assertEqual(
            by_operation["create_revenue_schedule"]["allocations"][0]["range"],
            "A1:J32",
        )
        self.assertEqual(
            by_operation["add_integrity_checks"]["allocations"][0]["range"],
            "A1:F10",
        )
        rendered = str(plan).lower()
        for forbidden in ("cell_write", "formula", "macro", "vba", "workbook_bytes"):
            self.assertNotIn(forbidden, rendered)

    def test_period_width_is_explicit(self) -> None:
        _, analysis, patch, resolution = contracts(budget_request())
        plan = plan_workbook_coordinates(
            analysis,
            patch,
            resolution,
            forecast_period_count=3,
        )
        forecast = next(
            item
            for item in plan["operation_plans"]
            if item["source_operation"] == "add_forecast_periods"
        )
        ranges = {item["sheet_name"]: item["range"] for item in forecast["allocations"]}
        self.assertEqual(ranges["Income Statement"], "E1:G5")
        self.assertEqual(ranges["Balance Sheet"], "D1:F5")

    def test_planned_valuation_sections_do_not_overlap(self) -> None:
        _, analysis, patch, resolution = contracts(dcf_request())
        plan = plan_workbook_coordinates(
            analysis,
            patch,
            resolution,
            forecast_period_count=5,
        )
        valuation = next(
            item for item in plan["sheet_plan"] if item["sheet_name"] == "Valuation"
        )
        self.assertEqual(
            valuation["planned_ranges"],
            ["A1:J24", "A27:J44", "A47:H56", "A59:H70", "A73:J84"],
        )
        self.assertTrue(plan["ready_for_executor"])

    def test_excel_column_limit_blocks_extension(self) -> None:
        workbook_map, _, _, _ = contracts(budget_request())
        sheets = tuple(
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
            sheets=sheets,
            findings=workbook_map.findings,
            limitations=workbook_map.limitations,
        )
        analysis = analyse_workbook_map(constrained_map, budget_request())
        patch = compile_workbook_patch(analysis).to_dict()
        resolution = resolve_workbook_patch_targets(analysis, patch).to_dict()
        plan = plan_workbook_coordinates(
            analysis,
            patch,
            resolution,
            forecast_period_count=5,
        )
        self.assertFalse(plan["ready_for_executor"])
        self.assertTrue(
            any("range_exceeds_excel_column_limit" in item for item in plan["blockers"])
        )

    def test_validator_detects_tampering(self) -> None:
        _, analysis, patch, resolution = contracts(budget_request())
        plan = plan_workbook_coordinates(
            analysis,
            patch,
            resolution,
            forecast_period_count=5,
        )
        tampered = copy.deepcopy(plan)
        tampered["operation_plans"][1]["allocations"][0]["range"] = "E1:J5"
        issues = validate_workbook_coordinate_plan_payload(
            tampered,
            analysis=analysis,
            patch=patch,
            target_resolution=resolution,
            forecast_period_count=5,
        )
        self.assertIn("coordinate_plan_id does not match payload", issues)
        self.assertIn(
            "coordinate plan does not match deterministic recomputation",
            issues,
        )

    def test_forecast_period_count_fails_closed(self) -> None:
        _, analysis, patch, resolution = contracts(budget_request())
        for value in (0, 61, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    plan_workbook_coordinates(
                        analysis,
                        patch,
                        resolution,
                        forecast_period_count=value,
                    )


if __name__ == "__main__":
    unittest.main()
