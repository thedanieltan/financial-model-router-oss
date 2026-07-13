from __future__ import annotations

import copy
import unittest
from dataclasses import replace

from fmr.model_specs import MODEL_DEFINITIONS
from fmr.types import ModelRequest
from fmr.workbook import (
    OPERATION_SPECS,
    WorkbookMap,
    analyse_workbook_map,
    compile_workbook_patch,
    inspect_workbook_bytes,
    operation_spec_registry_payload,
    resolve_workbook_patch_targets,
    validate_workbook_target_resolution_payload,
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


class TargetResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workbook_map = inspect_workbook_bytes(
            financial_workbook(),
            filename="synthetic.xlsx",
        )
        self.analysis = analyse_workbook_map(self.workbook_map, budget_request())
        self.patch = compile_workbook_patch(self.analysis).to_dict()

    def test_operation_registry_covers_every_model_operation(self) -> None:
        required = {
            operation
            for definition in MODEL_DEFINITIONS
            for operation in definition.operations
            if operation not in {"preserve_existing_workbook", "request_missing_inputs"}
        }
        self.assertEqual(set(OPERATION_SPECS), required)
        registry = operation_spec_registry_payload()
        self.assertEqual(
            registry["contract_version"],
            "workbook-operation-spec-registry.v1",
        )
        self.assertEqual(len(registry["registry_sha256"]), 64)
        self.assertEqual(len(registry["specifications"]), len(required))

    def test_budget_targets_are_resolved_without_cell_instructions(self) -> None:
        result = resolve_workbook_patch_targets(
            self.analysis,
            self.patch,
        ).to_dict()
        self.assertEqual(
            result["contract_version"],
            "workbook-target-resolution.v1",
        )
        self.assertTrue(result["ready_for_executor"])
        self.assertFalse(result["execution_supported_by_this_release"])
        self.assertEqual(
            validate_workbook_target_resolution_payload(
                result,
                analysis=self.analysis,
                patch=self.patch,
            ),
            (),
        )
        by_operation = {
            item["source_operation"]: item for item in result["resolutions"]
        }
        self.assertEqual(
            by_operation["create_assumptions_section"]["status"],
            "resolved_existing",
        )
        self.assertEqual(
            set(by_operation["add_forecast_periods"]["target"]["sheet_names"]),
            {"Income Statement", "Balance Sheet"},
        )
        self.assertEqual(
            by_operation["create_revenue_schedule"]["status"],
            "resolved_new",
        )
        rendered = str(result).lower()
        for forbidden in ("cell_address", "cell_write", "formula", "macro", "vba"):
            self.assertNotIn(forbidden, rendered)

    def test_later_operations_reuse_a_sheet_planned_earlier(self) -> None:
        analysis = analyse_workbook_map(self.workbook_map, dcf_request())
        patch = compile_workbook_patch(analysis).to_dict()
        result = resolve_workbook_patch_targets(analysis, patch).to_dict()
        valuation = [
            item
            for item in result["resolutions"]
            if item["target"]["canonical_sheet_name"] == "Valuation"
        ]
        self.assertGreaterEqual(len(valuation), 4)
        self.assertEqual(valuation[0]["status"], "resolved_new")
        self.assertTrue(
            all(item["status"] == "resolved_planned" for item in valuation[1:])
        )
        self.assertTrue(
            all(item["target"]["sheet_names"] == ["Valuation"] for item in valuation)
        )

    def test_ambiguous_existing_target_blocks_resolution(self) -> None:
        assumptions = next(
            sheet for sheet in self.workbook_map.sheets if sheet.name == "Assumptions"
        )
        duplicate = replace(
            assumptions,
            name="Inputs",
            position=self.workbook_map.sheet_count + 1,
        )
        ambiguous_map = WorkbookMap(
            source_filename=self.workbook_map.source_filename,
            source_sha256=self.workbook_map.source_sha256,
            source_size_bytes=self.workbook_map.source_size_bytes,
            sheet_count=self.workbook_map.sheet_count + 1,
            defined_names=self.workbook_map.defined_names,
            external_links_detected=self.workbook_map.external_links_detected,
            sheets=self.workbook_map.sheets + (duplicate,),
            findings=self.workbook_map.findings,
            limitations=self.workbook_map.limitations,
        )
        analysis = analyse_workbook_map(ambiguous_map, budget_request())
        patch = compile_workbook_patch(analysis).to_dict()
        result = resolve_workbook_patch_targets(analysis, patch).to_dict()
        assumptions_resolution = next(
            item
            for item in result["resolutions"]
            if item["source_operation"] == "create_assumptions_section"
        )
        self.assertEqual(assumptions_resolution["status"], "blocked")
        self.assertFalse(result["ready_for_executor"])
        self.assertTrue(
            any("ambiguous_target:assumptions" in item for item in result["blockers"])
        )

    def test_required_financial_statement_role_is_not_invented(self) -> None:
        request = ModelRequest(
            objective="build an integrated three-statement model",
            role="finance_manager",
            available_data=(
                "income_statement_history",
                "balance_sheet_history",
                "cash_flow_history",
                "capital_expenditure_schedule",
                "working_capital_schedule",
                "debt_schedule",
            ),
            workbook_capabilities=("historical_periods",),
            assumptions=("forecast_horizon", "tax_rate"),
        )
        analysis = analyse_workbook_map(self.workbook_map, request)
        patch = compile_workbook_patch(analysis).to_dict()
        result = resolve_workbook_patch_targets(analysis, patch).to_dict()
        link_resolution = next(
            item
            for item in result["resolutions"]
            if item["source_operation"] == "link_financial_statements"
        )
        self.assertEqual(link_resolution["status"], "blocked")
        self.assertIn(
            "missing_required_sheet_role:cash_flow_statement",
            link_resolution["blockers"],
        )

    def test_validator_detects_resolution_tampering(self) -> None:
        result = resolve_workbook_patch_targets(
            self.analysis,
            self.patch,
        ).to_dict()
        tampered = copy.deepcopy(result)
        tampered["resolutions"][0]["target"]["sheet_names"] = ["Other"]
        issues = validate_workbook_target_resolution_payload(
            tampered,
            analysis=self.analysis,
            patch=self.patch,
        )
        self.assertIn("resolution_id does not match payload", issues)
        self.assertIn(
            "target resolution does not match deterministic recomputation",
            issues,
        )


if __name__ == "__main__":
    unittest.main()
