from __future__ import annotations

import hashlib
import json
from typing import Any

from fmr.workflow import compile_workflow, validate_workflow_plan, workflow_rerun_plan


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def validate_workflow_acceptance_corpus(value: Any) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(value, dict) or value.get("contract_version") != "workflow-acceptance-corpus.v1":
        return ("workflow-acceptance-corpus.v1 is required",)
    required = {"contract_version", "corpus_id", "corpus_version", "cases", "practitioner_reviews"}
    if set(value) != required:
        issues.append("workflow acceptance corpus fields do not match the contract")
        return tuple(issues)
    if not isinstance(value.get("corpus_id"), str) or not value["corpus_id"]:
        issues.append("corpus_id is required")
    if not isinstance(value.get("corpus_version"), str) or not value["corpus_version"]:
        issues.append("corpus_version is required")
    cases = value.get("cases")
    if not isinstance(cases, list) or not cases:
        issues.append("workflow acceptance corpus must contain cases")
        return tuple(issues)
    case_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            issues.append("workflow acceptance cases must be objects")
            continue
        required_case = {"case_id", "data_classification", "request", "expected", "rerun_probe"}
        if set(case) != required_case:
            issues.append("workflow acceptance case fields do not match the contract")
            continue
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            issues.append("workflow acceptance case_id is required")
        elif case_id in case_ids:
            issues.append("workflow acceptance case identifiers must be unique")
        else:
            case_ids.add(case_id)
        if case.get("data_classification") not in {"synthetic", "anonymized"}:
            issues.append(f"workflow acceptance case data_classification is invalid:{case_id}")
        if not isinstance(case.get("request"), dict):
            issues.append(f"workflow acceptance case request is invalid:{case_id}")
        expected = case.get("expected")
        if not isinstance(expected, dict) or set(expected) != {"blueprint_id", "status", "step_states", "missing_requirements"}:
            issues.append(f"workflow acceptance expected result is invalid:{case_id}")
        rerun = case.get("rerun_probe")
        if rerun is not None and (
            not isinstance(rerun, dict)
            or set(rerun) != {"changed_inputs", "invalidated_steps", "reusable_steps"}
        ):
            issues.append(f"workflow acceptance rerun probe is invalid:{case_id}")
    reviews = value.get("practitioner_reviews")
    if not isinstance(reviews, list):
        issues.append("practitioner_reviews must be an array")
    return tuple(sorted(set(issues)))


def create_workflow_practitioner_review(
    case_result: dict[str, Any],
    *,
    reviewer_role: str,
    status: str,
    evidence_reference: str,
) -> dict[str, Any]:
    if status not in {"accepted", "rejected"}:
        raise ValueError("workflow practitioner review status is invalid")
    for field, value in (("reviewer_role", reviewer_role), ("evidence_reference", evidence_reference)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} is required")
    provisional = {
        "contract_version": "workflow-practitioner-review.v1",
        "case_id": case_result["case_id"],
        "case_sha256": case_result["case_sha256"],
        "plan_sha256": case_result["plan_sha256"],
        "reviewer_role": reviewer_role.strip(),
        "status": status,
        "evidence_reference": evidence_reference.strip(),
    }
    return {**provisional, "review_sha256": _digest(provisional)}


def validate_workflow_practitioner_review(value: Any) -> tuple[str, ...]:
    if not isinstance(value, dict) or value.get("contract_version") != "workflow-practitioner-review.v1":
        return ("workflow-practitioner-review.v1 is required",)
    required = {"contract_version", "case_id", "case_sha256", "plan_sha256", "reviewer_role", "status", "evidence_reference", "review_sha256"}
    issues: list[str] = []
    if set(value) != required:
        issues.append("workflow practitioner review fields do not match the contract")
        return tuple(issues)
    if value.get("status") not in {"accepted", "rejected"}:
        issues.append("workflow practitioner review status is invalid")
    provisional = {key: value[key] for key in value if key != "review_sha256"}
    if value.get("review_sha256") != _digest(provisional):
        issues.append("workflow practitioner review hash does not match")
    return tuple(sorted(set(issues)))


def run_workflow_acceptance_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    issues = validate_workflow_acceptance_corpus(corpus)
    if issues:
        raise ValueError("invalid workflow acceptance corpus: " + "; ".join(issues))
    case_results: list[dict[str, Any]] = []
    for case in sorted(corpus["cases"], key=lambda item: item["case_id"]):
        case_sha256 = _digest(case)
        case_issues: list[str] = []
        plan: dict[str, Any] | None = None
        try:
            plan = compile_workflow(case["request"])
            plan_issues = validate_workflow_plan(plan)
            if plan_issues:
                case_issues.extend(plan_issues)
            expected = case["expected"]
            if plan["blueprint"]["blueprint_id"] != expected["blueprint_id"]:
                case_issues.append("unexpected_blueprint")
            if plan["status"] != expected["status"]:
                case_issues.append("unexpected_plan_status")
            states = {step["step_id"]: step["status"] for step in plan["steps"]}
            if states != expected["step_states"]:
                case_issues.append("unexpected_step_states")
            if plan["missing_requirements"] != sorted(expected["missing_requirements"]):
                case_issues.append("unexpected_missing_requirements")
            rerun = case["rerun_probe"]
            rerun_result = None
            if rerun is not None:
                rerun_result = workflow_rerun_plan(plan, rerun["changed_inputs"])
                if rerun_result["invalidated_steps"] != sorted(rerun["invalidated_steps"]):
                    case_issues.append("unexpected_invalidated_steps")
                if rerun_result["reusable_steps"] != sorted(rerun["reusable_steps"]):
                    case_issues.append("unexpected_reusable_steps")
        except ValueError as exc:
            case_issues.append(str(exc))
            rerun_result = None
        result = {
            "case_id": case["case_id"],
            "case_sha256": case_sha256,
            "data_classification": case["data_classification"],
            "status": "passed" if not case_issues else "failed",
            "blueprint_id": plan["blueprint"]["blueprint_id"] if plan else None,
            "plan_sha256": plan["workflow_sha256"] if plan else None,
            "plan_status": plan["status"] if plan else None,
            "step_count": len(plan["steps"]) if plan else 0,
            "rerun_sha256": rerun_result["rerun_sha256"] if rerun_result else None,
            "issues": sorted(set(case_issues)),
        }
        case_results.append(result)
    implementation_status = "passed" if all(item["status"] == "passed" for item in case_results) else "failed"
    reviews_by_case: dict[str, list[dict[str, Any]]] = {}
    stale_review = False
    for review in corpus["practitioner_reviews"]:
        review_issues = validate_workflow_practitioner_review(review)
        if review_issues:
            stale_review = True
            continue
        reviews_by_case.setdefault(review["case_id"], []).append(review)
    accepted_reviews = True
    any_anonymized = False
    review_references: list[str] = []
    for result in case_results:
        if result["data_classification"] != "anonymized":
            accepted_reviews = False
            continue
        any_anonymized = True
        matching = [
            review
            for review in reviews_by_case.get(result["case_id"], [])
            if review["case_sha256"] == result["case_sha256"]
            and review["plan_sha256"] == result["plan_sha256"]
            and review["status"] == "accepted"
        ]
        if not matching:
            accepted_reviews = False
            if reviews_by_case.get(result["case_id"]):
                stale_review = True
        else:
            review_references.extend(review["evidence_reference"] for review in matching)
    practitioner_status = "accepted" if any_anonymized and accepted_reviews and implementation_status == "passed" else "pending"
    blockers: list[str] = []
    if implementation_status != "passed":
        blockers.append("workflow_implementation_acceptance_failed")
    if practitioner_status != "accepted":
        blockers.append("practitioner_review_incomplete")
    if stale_review:
        blockers.append("stale_practitioner_review_reference")
    deployment_status = "not_run"
    blockers.append("deployment_acceptance_not_run")
    production_status = "not_accepted"
    provisional = {
        "contract_version": "workflow-acceptance-result.v1",
        "corpus_id": corpus["corpus_id"],
        "corpus_version": corpus["corpus_version"],
        "corpus_sha256": _digest(corpus),
        "implementation_status": implementation_status,
        "practitioner_status": practitioner_status,
        "deployment_status": deployment_status,
        "production_status": production_status,
        "case_results": case_results,
        "review_references": sorted(set(review_references)),
        "blockers": sorted(set(blockers)),
    }
    return {
        **provisional,
        "acceptance_id": f"fmrwa_{_digest(provisional)[:24]}",
        "acceptance_sha256": _digest(provisional),
    }


def validate_workflow_acceptance_result(value: Any, *, corpus: dict[str, Any] | None = None) -> tuple[str, ...]:
    if not isinstance(value, dict) or value.get("contract_version") != "workflow-acceptance-result.v1":
        return ("workflow-acceptance-result.v1 is required",)
    required = {"contract_version", "acceptance_id", "acceptance_sha256", "corpus_id", "corpus_version", "corpus_sha256", "implementation_status", "practitioner_status", "deployment_status", "production_status", "case_results", "review_references", "blockers"}
    issues: list[str] = []
    if set(value) != required:
        issues.append("workflow acceptance result fields do not match the contract")
        return tuple(issues)
    provisional = {key: value[key] for key in value if key not in {"acceptance_id", "acceptance_sha256"}}
    expected_digest = _digest(provisional)
    if value.get("acceptance_id") != f"fmrwa_{expected_digest[:24]}":
        issues.append("workflow acceptance id does not match")
    if value.get("acceptance_sha256") != expected_digest:
        issues.append("workflow acceptance hash does not match")
    if corpus is not None:
        if value.get("corpus_sha256") != _digest(corpus):
            issues.append("workflow acceptance corpus hash does not match")
        expected = run_workflow_acceptance_corpus(corpus)
        if value != expected:
            issues.append("workflow acceptance result is not reproducible")
    return tuple(sorted(set(issues)))


__all__ = [
    "create_workflow_practitioner_review",
    "run_workflow_acceptance_corpus",
    "validate_workflow_acceptance_corpus",
    "validate_workflow_acceptance_result",
    "validate_workflow_practitioner_review",
]
