from __future__ import annotations

import copy
import unittest
from typing import Any

from fmr.types import ModelRequest
from fmr.workbook import (
    WorkbookAnalysis,
    analyse_workbook_map,
    compile_workbook_patch,
    inspect_workbook_bytes,
    validate_workbook_patch_payload,
    validate_workbook_patch_receipt_payload,
)
from tests.xlsx_factory import financial_workbook


def ready_request() -> ModelRequest:
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


def nested_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.add(str(key).lower())
            keys.update(nested_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.update(nested_keys(item))
    return keys


class WorkbookPatchTests(unittest.TestCase):
    def setUp(self) -> None:
        workbook_map = inspect_workbook_bytes(
            financial_workbook(),
            filename="synthetic.xlsx",
        )
        self.analysis = analyse_workbook_map(workbook_map, ready_request())
        self.patch = compile_workbook_patch(self.analysis).to_dict()

    def test_patch_is_deterministic_and_source_pinned(self) -> None:
        repeated = compile_workbook_patch(self.analysis).to_dict()
        self.assertEqual(repeated, self.patch)
        self.assertEqual(self.patch["contract_version"], "workbook-patch.v1")
        self.assertEqual(
            self.patch["source"]["sha256"],
            self.analysis.workbook_map.source_sha256,
        )
        self.assertTrue(self.patch["ready_for_executor"])
        self.assertFalse(self.patch["execution_supported_by_this_release"])
        self.assertEqual(validate_workbook_patch_payload(self.patch), ())

    def test_operations_are_additive_and_rollback_reverses_order(self) -> None:
        operation_ids = [item["operation_id"] for item in self.patch["operations"]]
        rollback_ids = [item["operation_id"] for item in self.patch["rollback_plan"]]
        self.assertEqual(rollback_ids, list(reversed(operation_ids)))
        self.assertTrue(
            all(item["mode"] == "additive" for item in self.patch["operations"])
        )
        self.assertTrue(
            nested_keys(self.patch).isdisjoint(
                {"workbook_bytes", "cell", "cell_write", "formula", "macro", "script", "vba"}
            )
        )

    def test_not_ready_analysis_produces_patch_blockers(self) -> None:
        workbook_map = self.analysis.workbook_map
        blocked = analyse_workbook_map(
            workbook_map,
            ModelRequest(
                objective="build a budget forecast",
                role="finance_manager",
                available_data=(),
                workbook_capabilities=(),
                assumptions=(),
            ),
        )
        patch = compile_workbook_patch(blocked).to_dict()
        self.assertFalse(patch["ready_for_executor"])
        self.assertTrue(
            any(item.startswith("analysis_not_ready:") for item in patch["blockers"])
        )
        self.assertEqual(validate_workbook_patch_payload(patch), ())

    def test_external_links_block_executor_readiness(self) -> None:
        workbook_map = inspect_workbook_bytes(
            financial_workbook(external_link=True),
            filename="external.xlsx",
        )
        analysis = analyse_workbook_map(workbook_map, ready_request())
        patch = compile_workbook_patch(analysis).to_dict()
        self.assertFalse(patch["ready_for_executor"])
        self.assertIn("external_links_detected", patch["blockers"])

    def test_validator_detects_tampering(self) -> None:
        tampered = copy.deepcopy(self.patch)
        tampered["operations"][0]["target"]["semantic_role"] = "unapproved"
        issues = validate_workbook_patch_payload(tampered)
        self.assertIn(
            "operations[0].target does not match source_operation",
            issues,
        )
        self.assertIn("patch_id does not match payload", issues)

    def test_workbook_analysis_round_trip_recomputes_contract(self) -> None:
        payload = self.analysis.to_dict()
        self.assertEqual(WorkbookAnalysis.from_mapping(payload), self.analysis)
        tampered = copy.deepcopy(payload)
        tampered["derived_evidence"]["available_data"].append("invented_input")
        with self.assertRaisesRegex(ValueError, "deterministic recomputation"):
            WorkbookAnalysis.from_mapping(tampered)

    def test_receipt_can_be_checked_against_patch(self) -> None:
        receipt = {
            "contract_version": "workbook-patch-receipt.v1",
            "patch_id": self.patch["patch_id"],
            "source_sha256": self.patch["source"]["sha256"],
            "output_sha256": "b" * 64,
            "status": "applied",
            "operation_receipts": [
                {
                    "operation_id": operation["operation_id"],
                    "status": "applied",
                    "before_state_sha256": "c" * 64,
                    "after_state_sha256": "d" * 64,
                    "rollback_state_sha256": None,
                    "affected_parts": ["xl/workbook.xml"],
                }
                for operation in self.patch["operations"]
            ],
            "validations": [
                {
                    "check": "output_reopens_as_xlsx",
                    "passed": True,
                    "message": "output archive reopened",
                }
            ],
        }
        self.assertEqual(
            validate_workbook_patch_receipt_payload(receipt, patch=self.patch),
            (),
        )
        receipt["patch_id"] = "fmrp_" + "0" * 24
        self.assertIn(
            "receipt patch_id does not match patch",
            validate_workbook_patch_receipt_payload(receipt, patch=self.patch),
        )


if __name__ == "__main__":
    unittest.main()
