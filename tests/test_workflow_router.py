from __future__ import annotations

import copy
import hashlib
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
from fmr.workflow import compile_workflow, execute_workflow, validate_workflow_plan, workflow_rerun_plan
from fmr.workflow_acceptance import (
    create_workflow_practitioner_review,
    run_workflow_acceptance_corpus,
    validate_workflow_acceptance_corpus,
    validate_workflow_acceptance_result,
    validate_workflow_practitioner_review,
)


def _corpus() -> dict:
    return json.loads(files("fmr.fixtures").joinpath("acceptance/synthetic-practitioner-workflows.v1.json").read_text(encoding="utf-8"))


def _dcf_request(root: Path) -> dict:
    model_corpus = json.loads(files("fmr.fixtures").joinpath("acceptance/synthetic-initial-families.v1.json").read_text(encoding="utf-8"))
    case = next(item for item in model_corpus["cases"] if item["job"]["model_family"] == "operating_company_dcf")
    source = root / "canonical.json"
    payload = json.dumps(case["canonical_input"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    source.write_bytes(payload)
    return {
        "contract_version": "finance-workflow-request.v1",
        "objective": "Value the operating company using a DCF and show enterprise and equity value",
        "role": "private_equity",
        "entity_id": "synthetic-company",
        "reporting_period": "2025",
        "requested_outputs": ["enterprise_value", "equity_value", "operating_company_dcf"],
        "available_data": case["job"]["available_data"],
        "available_assumptions": case["job"]["available_assumptions"],
        "input_references": {
            "canonical": {
                "contract_version": "canonical-financial-data.v2",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "path": str(source),
            }
        },
        "industry": None,
        "output_formats": ["json"],
        "policy_name": "local-only",
        "constraints": {"local_only": True, "open_source_only": True, "network_allowed": False},
        "context": {},
    }


class WorkflowRouterTests(unittest.TestCase):
    def test_bundled_acceptance_corpus_covers_supported_and_blocked_workflows(self) -> None:
        corpus = _corpus()
        self.assertEqual(validate_workflow_acceptance_corpus(corpus), ())
        result = run_workflow_acceptance_corpus(corpus)
        self.assertEqual(result["implementation_status"], "passed")
        self.assertEqual(result["practitioner_status"], "pending")
        self.assertEqual(result["production_status"], "not_accepted")
        self.assertEqual(validate_workflow_acceptance_result(result, corpus=corpus), ())
        self.assertEqual(
            {item["blueprint_id"] for item in result["case_results"]},
            {
                "monthly_forecast_update",
                "scenario_analysis",
                "operating_company_valuation",
                "debt_capacity_refresh",
                "project_finance_debt_sizing",
                "leveraged_buyout_screening",
                "venture_follow_on_analysis",
            },
        )
        self.assertEqual(result, run_workflow_acceptance_corpus(corpus))

    def test_workflow_contract_schemas_validate_request_plan_corpus_and_result(self) -> None:
        root = files("fmr.contracts")
        names = (
            "finance-workflow-request.v1.schema.json",
            "finance-workflow-plan.v1.schema.json",
            "workflow-rerun-plan.v1.schema.json",
            "workflow-practitioner-review.v1.schema.json",
            "workflow-acceptance-corpus.v1.schema.json",
            "workflow-acceptance-result.v1.schema.json",
        )
        documents = {name: json.loads(root.joinpath(name).read_text(encoding="utf-8")) for name in names}
        registry = Registry().with_resources((item["$id"], Resource.from_contents(item)) for item in documents.values())
        corpus = _corpus()
        plan = compile_workflow(corpus["cases"][0]["request"])
        result = run_workflow_acceptance_corpus(corpus)
        review = create_workflow_practitioner_review(
            result["case_results"][0],
            reviewer_role="qualified-finance-practitioner",
            status="accepted",
            evidence_reference="review://immutable/external-record",
        )
        Draft202012Validator(documents[names[0]], registry=registry).validate(corpus["cases"][0]["request"])
        Draft202012Validator(documents[names[1]], registry=registry).validate(plan)
        Draft202012Validator(documents[names[3]], registry=registry).validate(review)
        Draft202012Validator(documents[names[4]], registry=registry).validate(corpus)
        Draft202012Validator(documents[names[5]], registry=registry).validate(result)
        self.assertEqual(validate_workflow_practitioner_review(review), ())

    def test_plan_is_deterministic_and_rerun_invalidates_only_descendants(self) -> None:
        request = next(item["request"] for item in _corpus()["cases"] if item["case_id"] == "monthly-forecast")
        plan = compile_workflow(request)
        self.assertEqual(validate_workflow_plan(plan), ())
        self.assertEqual(plan, compile_workflow(copy.deepcopy(request)))
        rerun = workflow_rerun_plan(plan, ["revenue_growth_rate"])
        self.assertEqual(
            rerun["invalidated_steps"],
            ["assemble_outputs", "refresh_forecast", "refresh_statements", "review_forecast"],
        )
        self.assertEqual(rerun["reusable_steps"], ["validate_sources"])

    def test_unsupported_practitioner_work_is_honestly_blocked(self) -> None:
        for case_id in ("lbo-blocked", "project-finance-blocked", "venture-follow-on-blocked"):
            request = next(item["request"] for item in _corpus()["cases"] if item["case_id"] == case_id)
            plan = compile_workflow(request)
            self.assertEqual(plan["status"], "blocked")
            self.assertIn("route_status:unsupported_family", plan["missing_requirements"])
            self.assertFalse(any(step["route_decision"] and step["route_decision"]["status"] == "selected" for step in plan["steps"] if step["kind"] == "model"))

    def test_cli_http_and_python_compile_identical_plans(self) -> None:
        request = next(item["request"] for item in _corpus()["cases"] if item["case_id"] == "scenario-downside")
        expected = compile_workflow(request)
        response = TestClient(create_app()).post("/api/v2/workflows/plans", json=request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path, plan_path = root / "request.json", root / "plan.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            self.assertEqual(main(["compile-workflow", str(request_path), "--output", str(plan_path)]), 0)
            self.assertEqual(json.loads(plan_path.read_text()), expected)

    def test_real_dcf_provider_executes_inside_workflow_and_requires_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = compile_workflow(_dcf_request(root))
            pending = execute_workflow(plan, idempotency_key="dcf-workflow", output_dir=root / "pending")
            self.assertEqual(pending["state"], "awaiting_approval")
            accepted = execute_workflow(
                plan,
                idempotency_key="dcf-workflow-approved",
                output_dir=root / "accepted",
                approvals={"review_valuation": True},
            )
            self.assertEqual(accepted["state"], "completed")
            model_step = next(item for item in accepted["step_results"] if item["step_id"] == "calculate_dcf")
            self.assertEqual(model_step["state"], "completed")
            self.assertEqual(model_step["execution_result"]["provider"]["provider_id"], "python-forecast")

    def test_anonymized_cases_require_matching_practitioner_reviews(self) -> None:
        corpus = _corpus()
        for case in corpus["cases"]:
            case["data_classification"] = "anonymized"
        initial = run_workflow_acceptance_corpus(corpus)
        corpus["practitioner_reviews"] = [
            create_workflow_practitioner_review(
                case_result,
                reviewer_role="qualified-finance-practitioner",
                status="accepted",
                evidence_reference=f"review://external/{case_result['case_id']}",
            )
            for case_result in initial["case_results"]
        ]
        accepted = run_workflow_acceptance_corpus(corpus)
        self.assertEqual(accepted["practitioner_status"], "accepted")
        self.assertEqual(accepted["production_status"], "accepted")
        stale = copy.deepcopy(corpus)
        stale["cases"][0]["request"]["objective"] += " now"
        pending = run_workflow_acceptance_corpus(stale)
        self.assertEqual(pending["practitioner_status"], "pending")
        self.assertIn("stale_practitioner_review_reference", pending["blockers"])


if __name__ == "__main__":
    unittest.main()
