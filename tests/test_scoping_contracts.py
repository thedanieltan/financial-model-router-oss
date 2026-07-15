from __future__ import annotations

import copy
import json
import unittest
from importlib.resources import files

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from fmr.core import (
    ModelJob,
    create_model_intent,
    create_scope_assessment,
    create_scope_candidate,
    create_scope_confirmation,
    validate_model_intent,
    validate_scope_assessment,
    validate_scope_candidate,
    validate_scope_confirmation,
)


def _lifecycle() -> tuple[dict, dict, dict, dict]:
    intent = create_model_intent({
        "objective": "Plan next year's operations",
        "decision_context": "operating_plan",
        "requested_outcomes": ["operating plan"],
        "planning_horizon": {"value": 1, "unit": "years"},
        "available_data": ["income_statement_history"],
        "output_formats": ["json"],
    })
    candidate = create_scope_candidate({
        "family_id": "budget_forecast",
        "title": "Budget and forecast",
        "purpose": "Project operating performance and funding needs.",
        "suitability": "possible",
        "supporting_evidence": ["decision_context:operating_plan"],
        "missing_information": ["revenue_drivers"],
        "limitations": ["Not a valuation opinion."],
        "deliverables": ["budget_forecast"],
        "knowledge_references": ["family:budget_forecast@1.0.0"],
    })
    assessment = create_scope_assessment(
        intent=intent,
        state="candidate_scopes",
        candidates=[candidate],
        knowledge_base_version="1.0.0",
    )
    confirmation = create_scope_confirmation(
        assessment,
        selected_family="budget_forecast",
        acknowledged_limitations=["Not a valuation opinion."],
    )
    return intent, candidate, assessment, confirmation


class ScopingContractTests(unittest.TestCase):
    def test_scoping_lifecycle_is_hash_pinned_and_schema_valid(self) -> None:
        intent, candidate, assessment, confirmation = _lifecycle()
        self.assertEqual(validate_model_intent(intent), ())
        self.assertEqual(validate_scope_candidate(candidate), ())
        self.assertEqual(validate_scope_assessment(assessment), ())
        self.assertEqual(validate_scope_confirmation(confirmation), ())
        validators = _validators()
        for name, value in (
            ("model-intent.v1.schema.json", intent),
            ("model-scope-candidate.v1.schema.json", candidate),
            ("model-scope-assessment.v1.schema.json", assessment),
            ("scope-confirmation.v1.schema.json", confirmation),
        ):
            validators[name].validate(value)

    def test_confirmation_is_pinned_into_model_job_and_handoff_hash_chain(self) -> None:
        _, _, _, confirmation = _lifecycle()
        job = ModelJob.from_mapping({
            "contract_version": "model-job.v2",
            "objective": "Plan next year's operations",
            "model_family": "budget_forecast",
            "requested_deliverables": ["budget_forecast"],
            "output_formats": ["json"],
            "scope_confirmation": confirmation,
        })
        self.assertEqual(job.to_dict()["scope_confirmation"]["confirmation_id"], confirmation["confirmation_id"])
        with self.assertRaisesRegex(ValueError, "must match model_family"):
            ModelJob.from_mapping({**job.to_dict(), "model_family": "operating_company_dcf"})

    def test_forged_id_and_unacknowledged_limitations_fail_closed(self) -> None:
        _, _, assessment, confirmation = _lifecycle()
        forged = copy.deepcopy(confirmation)
        forged["selected_family"] = "operating_company_dcf"
        self.assertTrue(validate_scope_confirmation(forged))
        with self.assertRaisesRegex(ValueError, "every candidate limitation"):
            create_scope_confirmation(assessment, selected_family="budget_forecast", acknowledged_limitations=[])


def _validators() -> dict[str, Draft202012Validator]:
    root = files("fmr.contracts")
    names = (
        "model-intent.v1.schema.json",
        "model-scope-candidate.v1.schema.json",
        "model-scope-assessment.v1.schema.json",
        "scope-confirmation.v1.schema.json",
    )
    documents = {name: json.loads(root.joinpath(name).read_text(encoding="utf-8")) for name in names}
    registry = Registry().with_resources((document["$id"], Resource.from_contents(document)) for document in documents.values())
    return {name: Draft202012Validator(document, registry=registry) for name, document in documents.items()}


if __name__ == "__main__":
    unittest.main()
