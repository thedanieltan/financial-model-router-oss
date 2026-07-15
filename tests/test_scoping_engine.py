from __future__ import annotations

import copy
import json
import unittest

import fmr.scoping_service as scoping_service
from fmr import (
    answer_scope_question,
    assess_model_intent,
    compile_confirmed_scope,
    create_model_intent,
    create_scope_confirmation,
)
from fmr.core import ModelJob
from fmr.core.handoffs import digest


def _candidate(assessment: dict, family_id: str) -> dict:
    return next(item for item in assessment["candidates"] if item["family_id"] == family_id)


class GuidedScopingEngineTests(unittest.TestCase):
    def test_unknown_decision_requests_clarification_without_provider_discovery(self) -> None:
        intent = create_model_intent({
            "objective": "Help me understand this spreadsheet",
            "decision_context": "unknown",
            "output_formats": ["json"],
        })

        assessment = assess_model_intent(intent)

        self.assertEqual(assessment["state"], "clarification_required")
        self.assertIn("What decision should the model help you make?", assessment["clarification_questions"])
        serialized = json.dumps(assessment, sort_keys=True)
        self.assertNotIn("provider_id", serialized)
        self.assertNotIn("package_id", serialized)
        self.assertFalse(hasattr(scoping_service, "ProviderRegistry"))

    def test_answering_primary_decision_reissues_intent_and_finds_budget_scope(self) -> None:
        intent = create_model_intent({
            "objective": "Help me plan the company",
            "output_formats": ["json"],
        })

        answered = answer_scope_question(intent, "primary-decision", "operating_plan")
        assessment = assess_model_intent(answered)

        self.assertNotEqual(answered["intent_id"], intent["intent_id"])
        self.assertEqual(answered["decision_context"], "operating_plan")
        self.assertEqual(assessment["state"], "candidate_scopes")
        self.assertEqual(_candidate(assessment, "budget_forecast")["suitability"], "possible")

    def test_valuation_without_forecast_blocks_dcf_and_surfaces_prerequisite_model(self) -> None:
        assessment = assess_model_intent(create_model_intent({
            "objective": "Estimate enterprise value",
            "decision_context": "valuation",
            "requested_outcomes": ["enterprise value"],
            "context": {"operating_forecast_available": "no"},
            "output_formats": ["json"],
        }))

        dcf = _candidate(assessment, "operating_company_dcf")
        linked = _candidate(assessment, "three_statement")
        self.assertEqual(dcf["suitability"], "blocked")
        self.assertIn("supported_operating_forecast", dcf["prerequisites"])
        self.assertEqual(linked["suitability"], "possible")
        with self.assertRaisesRegex(ValueError, "selectable"):
            create_scope_confirmation(
                assessment,
                selected_family="operating_company_dcf",
                acknowledged_limitations=dcf["limitations"],
            )

    def test_confirmed_ready_budget_scope_compiles_provider_neutral_model_job(self) -> None:
        intent = create_model_intent({
            "objective": "Prepare next year's operating budget",
            "decision_context": "operating_plan",
            "requested_outcomes": ["budget", "forecast"],
            "planning_horizon": {"value": 12, "unit": "months"},
            "available_data": ["income_statement_history", "operating_cost_drivers", "revenue_drivers"],
            "available_assumptions": [
                "forecast_horizon",
                "operating_cost_growth_rate",
                "revenue_growth_rate",
                "scenario",
                "scenario_adjustments",
            ],
            "output_formats": ["json"],
        })
        assessment = assess_model_intent(intent)
        candidate = _candidate(assessment, "budget_forecast")
        self.assertEqual(candidate["suitability"], "eligible")
        confirmation = create_scope_confirmation(
            assessment,
            selected_family="budget_forecast",
            acknowledged_limitations=candidate["limitations"],
        )

        job = compile_confirmed_scope(
            assessment,
            confirmation,
            input_references={
                "canonical_data": {
                    "contract_version": "canonical-financial-data.v1",
                    "sha256": "a" * 64,
                    "uri": "urn:fmr:test:canonical-data",
                }
            },
        )

        self.assertEqual(ModelJob.from_mapping(job).model_family, "budget_forecast")
        self.assertEqual(job["scope_confirmation"]["confirmation_id"], confirmation["confirmation_id"])
        self.assertNotIn("provider", job)

    def test_forged_confirmation_and_assessment_mismatch_fail_closed(self) -> None:
        assessment = assess_model_intent(create_model_intent({
            "objective": "Prepare a budget",
            "decision_context": "operating_plan",
            "requested_outcomes": ["budget"],
        }))
        candidate = _candidate(assessment, "budget_forecast")
        confirmation = create_scope_confirmation(
            assessment,
            selected_family="budget_forecast",
            acknowledged_limitations=candidate["limitations"],
        )
        forged = copy.deepcopy(confirmation)
        forged["assessment_sha256"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "invalid scope confirmation"):
            compile_confirmed_scope(assessment, forged)

        omitted = {
            key: value
            for key, value in confirmation.items()
            if key not in {"confirmation_id", "confirmation_sha256"}
        }
        omitted["acknowledged_limitations"] = []
        omitted_sha = digest(omitted)
        omitted = {
            **omitted,
            "confirmation_id": f"fmrc_{omitted_sha[:24]}",
            "confirmation_sha256": omitted_sha,
        }
        with self.assertRaisesRegex(ValueError, "acknowledge every"):
            compile_confirmed_scope(assessment, omitted)

    def test_contradictory_horizon_blocks_candidates(self) -> None:
        assessment = assess_model_intent(create_model_intent({
            "objective": "Prepare a forecast",
            "decision_context": "operating_plan",
            "requested_outcomes": ["forecast"],
            "planning_horizon": {"value": 12, "unit": "months"},
            "context": {"forecast_horizon_known": "no"},
        }))

        self.assertEqual(assessment["state"], "contradictory_requirements")
        self.assertTrue(assessment["candidates"])
        self.assertTrue(all(item["suitability"] == "blocked" for item in assessment["candidates"]))
        self.assertTrue(any("both supplied" in conflict for item in assessment["candidates"] for conflict in item["conflicting_evidence"]))

    def test_unknown_question_and_option_fail_closed(self) -> None:
        intent = create_model_intent({"objective": "Prepare a plan"})
        with self.assertRaisesRegex(ValueError, "unknown scope question"):
            answer_scope_question(intent, "missing-question", "yes")
        with self.assertRaisesRegex(ValueError, "not an allowed"):
            answer_scope_question(intent, "primary-decision", "invented")


if __name__ == "__main__":
    unittest.main()
