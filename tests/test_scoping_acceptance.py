from __future__ import annotations

import copy
import json
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from fmr.api.composed import create_app
from fmr.entrypoint import main
from fmr.scoping_acceptance import (
    create_scoping_practitioner_review,
    run_guided_scoping_acceptance_corpus,
    validate_guided_scoping_acceptance_corpus,
    validate_guided_scoping_acceptance_result,
    validate_scoping_practitioner_review,
)


def _corpus() -> dict:
    return json.loads(files("fmr.fixtures").joinpath("acceptance/synthetic-guided-scoping.v1.json").read_text(encoding="utf-8"))


class GuidedScopingAcceptanceTests(unittest.TestCase):
    def test_bundled_corpus_covers_states_families_and_workbook_boundary(self) -> None:
        corpus = _corpus()
        self.assertEqual(validate_guided_scoping_acceptance_corpus(corpus), ())
        result = run_guided_scoping_acceptance_corpus(corpus)
        self.assertEqual(result["implementation_status"], "passed")
        self.assertEqual(result["practitioner_status"], "pending")
        self.assertEqual(result["production_status"], "not_accepted")
        self.assertEqual(validate_guided_scoping_acceptance_result(result, corpus=corpus), ())
        self.assertEqual(
            {item["state"] for item in result["case_results"]},
            {"clarification_required", "candidate_scopes", "contradictory_requirements", "unsupported_scope"},
        )
        self.assertEqual(
            {item["selected_family"] for item in result["case_results"] if item["selected_family"]},
            {"budget_forecast", "three_statement", "operating_company_dcf", "debt_capacity_refinancing"},
        )
        workbook_case = next(item for item in result["case_results"] if item["case_id"] == "workbook-cannot-infer-intent")
        self.assertEqual(workbook_case["state"], "clarification_required")
        self.assertNotIn("objective", json.dumps(result))
        self.assertEqual(result, run_guided_scoping_acceptance_corpus(corpus))

    def test_contract_schemas_accept_corpus_review_and_result(self) -> None:
        root = files("fmr.contracts")
        names = (
            "guided-scoping-practitioner-review.v1.schema.json",
            "guided-scoping-acceptance-corpus.v1.schema.json",
            "guided-scoping-acceptance-result.v1.schema.json",
        )
        documents = {name: json.loads(root.joinpath(name).read_text(encoding="utf-8")) for name in names}
        registry = Registry().with_resources((item["$id"], Resource.from_contents(item)) for item in documents.values())
        corpus = _corpus()
        result = run_guided_scoping_acceptance_corpus(corpus)
        review = create_scoping_practitioner_review(
            result["case_results"][0], reviewer_role="qualified-finance-practitioner",
            status="accepted", evidence_reference="review://immutable/external-record",
        )
        Draft202012Validator(documents[names[0]], registry=registry).validate(review)
        Draft202012Validator(documents[names[1]], registry=registry).validate(corpus)
        Draft202012Validator(documents[names[2]], registry=registry).validate(result)
        self.assertEqual(validate_scoping_practitioner_review(review), ())

    def test_anonymized_corpus_needs_matching_accepted_review_for_every_case(self) -> None:
        corpus = _corpus()
        for case in corpus["cases"]:
            case["data_classification"] = "anonymized"
        initial = run_guided_scoping_acceptance_corpus(corpus)
        corpus["practitioner_reviews"] = [
            create_scoping_practitioner_review(
                case_result,
                reviewer_role="qualified-finance-practitioner",
                status="accepted",
                evidence_reference=f"review://external/{case_result['case_id']}",
            )
            for case_result in initial["case_results"]
        ]
        accepted = run_guided_scoping_acceptance_corpus(corpus)
        self.assertEqual(accepted["practitioner_status"], "accepted")
        self.assertEqual(accepted["production_status"], "accepted")

        stale = copy.deepcopy(corpus)
        stale["cases"][0]["intent"]["objective"] += " now"
        pending = run_guided_scoping_acceptance_corpus(stale)
        self.assertEqual(pending["practitioner_status"], "pending")
        self.assertIn("stale_practitioner_review_reference", pending["blockers"])

    def test_bad_expectation_and_forged_review_fail_closed(self) -> None:
        corpus = _corpus()
        corpus["cases"][1]["expected"]["candidates"][0]["suitability"] = "blocked"
        self.assertEqual(run_guided_scoping_acceptance_corpus(corpus)["implementation_status"], "failed")
        result = run_guided_scoping_acceptance_corpus(_corpus())
        review = create_scoping_practitioner_review(
            result["case_results"][0], reviewer_role="finance", status="accepted", evidence_reference="review://record",
        )
        review["status"] = "rejected"
        self.assertTrue(validate_scoping_practitioner_review(review))

    def test_cli_and_http_preserve_practitioner_gate(self) -> None:
        corpus = _corpus()
        expected = run_guided_scoping_acceptance_corpus(corpus)
        response = TestClient(create_app()).post("/api/v2/scoping/acceptance", json=corpus)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            corpus_path, result_path = root / "corpus.json", root / "result.json"
            corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
            self.assertEqual(main(["run-guided-scoping-acceptance", str(corpus_path), "--output", str(result_path)]), 0)
            self.assertEqual(json.loads(result_path.read_text()), expected)
            self.assertEqual(main(["run-guided-scoping-acceptance", str(corpus_path), "--require-practitioner", "--output", str(result_path)]), 2)


if __name__ == "__main__":
    unittest.main()
