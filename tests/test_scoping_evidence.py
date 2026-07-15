from __future__ import annotations

import copy
import unittest
from dataclasses import replace
from importlib.resources import files

from jsonschema import Draft202012Validator

from fmr import (
    apply_workbook_scope_evidence,
    assess_model_intent,
    create_model_intent,
    derive_workbook_scope_evidence,
    validate_workbook_scope_evidence,
)
from fmr.providers.native_xlsx.workbook import inspect_workbook_bytes
from fmr.core.handoffs import digest
from tests.xlsx_factory import financial_workbook


class WorkbookScopeEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workbook_map = inspect_workbook_bytes(financial_workbook(), filename="synthetic.xlsx")

    def test_evidence_is_deterministic_hash_pinned_and_schema_valid(self) -> None:
        first = derive_workbook_scope_evidence(self.workbook_map)
        second = derive_workbook_scope_evidence(self.workbook_map.to_dict())

        self.assertEqual(first, second)
        self.assertEqual(validate_workbook_scope_evidence(first), ())
        self.assertEqual(first["source"]["sha256"], self.workbook_map.source_sha256)
        self.assertEqual(set(first["observed_data"]), {"balance_sheet_history", "income_statement_history"})
        self.assertIn("Workbook structure cannot establish user intent or assumptions.", first["limitations"])
        schema = __import__("json").loads(files("fmr.contracts").joinpath("model-scope-workbook-evidence.v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(first)

    def test_enrichment_preserves_user_intent_and_never_adds_assumptions(self) -> None:
        intent = create_model_intent({
            "objective": "Help me understand the business",
            "decision_context": "unknown",
            "requested_outcomes": ["understand performance"],
            "available_data": ["cash_flow_history"],
            "available_assumptions": ["tax_rate"],
        })
        evidence = derive_workbook_scope_evidence(self.workbook_map)

        enriched = apply_workbook_scope_evidence(intent, evidence, workbook_map=self.workbook_map)

        self.assertEqual(enriched["objective"], intent["objective"])
        self.assertEqual(enriched["decision_context"], "unknown")
        self.assertEqual(enriched["requested_outcomes"], intent["requested_outcomes"])
        self.assertEqual(enriched["available_assumptions"], ["tax_rate"])
        self.assertEqual(
            set(enriched["available_data"]),
            {"balance_sheet_history", "cash_flow_history", "income_statement_history"},
        )
        self.assertEqual(assess_model_intent(enriched)["state"], "clarification_required")

    def test_tampered_or_wrong_workbook_evidence_fails_closed(self) -> None:
        intent = create_model_intent({"objective": "Prepare a plan"})
        evidence = derive_workbook_scope_evidence(self.workbook_map)
        tampered = copy.deepcopy(evidence)
        tampered["observed_data"].append("revenue_drivers")
        provisional = {key: value for key, value in tampered.items() if key not in {"evidence_id", "evidence_sha256"}}
        tampered_sha = digest(provisional)
        tampered["evidence_id"] = f"fmrwe_{tampered_sha[:24]}"
        tampered["evidence_sha256"] = tampered_sha
        self.assertTrue(any("observed_data does not match observations" in issue for issue in validate_workbook_scope_evidence(tampered)))
        with self.assertRaisesRegex(ValueError, "invalid workbook scope evidence"):
            apply_workbook_scope_evidence(intent, tampered, workbook_map=self.workbook_map)

        other = replace(self.workbook_map, source_sha256="b" * 64)
        with self.assertRaisesRegex(ValueError, "deterministic recomputation"):
            apply_workbook_scope_evidence(intent, evidence, workbook_map=other)

    def test_external_links_are_visible_and_existing_evidence_cannot_be_overwritten(self) -> None:
        linked_map = replace(self.workbook_map, external_links_detected=True)
        evidence = derive_workbook_scope_evidence(linked_map)
        self.assertEqual(evidence["warnings"], ["external workbook links were detected"])
        intent = create_model_intent({"objective": "Prepare a plan"})
        enriched = apply_workbook_scope_evidence(intent, evidence, workbook_map=linked_map)
        with self.assertRaisesRegex(ValueError, "already contains"):
            apply_workbook_scope_evidence(enriched, evidence, workbook_map=linked_map)

    def test_invalid_explicit_capabilities_are_not_silently_replaced(self) -> None:
        intent = create_model_intent({
            "objective": "Prepare a plan",
            "context": {"workbook_capabilities": "unknown"},
        })
        evidence = derive_workbook_scope_evidence(self.workbook_map)
        with self.assertRaisesRegex(ValueError, "must be an array"):
            apply_workbook_scope_evidence(intent, evidence, workbook_map=self.workbook_map)


if __name__ == "__main__":
    unittest.main()
