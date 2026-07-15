from __future__ import annotations

import re
from typing import Any

from fmr.core import create_model_intent, create_scope_confirmation
from fmr.core.handoffs import digest
from fmr.scoping_evidence import apply_workbook_scope_evidence, derive_workbook_scope_evidence
from fmr.scoping_service import assess_model_intent, compile_confirmed_scope


_IDENTIFIER = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")
_SEMVER = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_HEX_64 = re.compile(r"[a-f0-9]{64}")
_STATES = {"clarification_required", "candidate_scopes", "unsupported_scope", "contradictory_requirements"}
_SUITABILITY = {"eligible", "possible", "blocked", "unsupported"}


def create_scoping_practitioner_review(
    case_result: dict[str, Any],
    *,
    reviewer_role: str,
    status: str,
    evidence_reference: str,
) -> dict[str, Any]:
    if not isinstance(case_result, dict) or not isinstance(case_result.get("case_id"), str) or not _HEX_64.fullmatch(case_result.get("case_sha256", "")) or not _HEX_64.fullmatch(case_result.get("assessment_sha256", "")):
        raise ValueError("case result does not contain a reviewable assessment")
    if not isinstance(reviewer_role, str) or not reviewer_role:
        raise ValueError("reviewer_role is required")
    if status not in {"accepted", "rejected"}:
        raise ValueError("review status is invalid")
    if not isinstance(evidence_reference, str) or not evidence_reference:
        raise ValueError("evidence_reference is required")
    provisional = {
        "contract_version": "guided-scoping-practitioner-review.v1",
        "case_id": case_result["case_id"],
        "case_sha256": case_result["case_sha256"],
        "assessment_sha256": case_result["assessment_sha256"],
        "reviewer_role": reviewer_role,
        "status": status,
        "evidence_reference": evidence_reference,
    }
    sha = digest(provisional)
    return {**provisional, "review_id": f"fmrsr_{sha[:24]}", "review_sha256": sha}


def validate_scoping_practitioner_review(value: Any) -> tuple[str, ...]:
    expected = {"contract_version", "review_id", "review_sha256", "case_id", "case_sha256", "assessment_sha256", "reviewer_role", "status", "evidence_reference"}
    if not isinstance(value, dict) or value.get("contract_version") != "guided-scoping-practitioner-review.v1":
        return ("unsupported guided scoping practitioner review contract",)
    issues = []
    if set(value) != expected:
        issues.append("guided scoping practitioner review fields do not match the contract")
    if not isinstance(value.get("case_id"), str) or not _IDENTIFIER.fullmatch(value["case_id"]):
        issues.append("guided scoping practitioner review case_id is invalid")
    for field in ("case_sha256", "assessment_sha256"):
        if not isinstance(value.get(field), str) or not _HEX_64.fullmatch(value[field]):
            issues.append(f"guided scoping practitioner review {field} is invalid")
    for field in ("reviewer_role", "evidence_reference"):
        if not isinstance(value.get(field), str) or not value[field]:
            issues.append(f"guided scoping practitioner review {field} is required")
    if value.get("status") not in {"accepted", "rejected"}:
        issues.append("guided scoping practitioner review status is invalid")
    provisional = {key: item for key, item in value.items() if key not in {"review_id", "review_sha256"}}
    sha = digest(provisional)
    if value.get("review_sha256") != sha or value.get("review_id") != f"fmrsr_{sha[:24]}":
        issues.append("guided scoping practitioner review identity does not match canonical payload")
    return tuple(dict.fromkeys(issues))


def validate_guided_scoping_acceptance_corpus(value: Any) -> tuple[str, ...]:
    if not isinstance(value, dict) or value.get("contract_version") != "guided-scoping-acceptance-corpus.v1":
        return ("unsupported guided scoping acceptance corpus contract",)
    issues: list[str] = []
    if set(value) != {"contract_version", "corpus_id", "corpus_version", "cases", "practitioner_reviews"}:
        issues.append("guided scoping acceptance corpus fields do not match the contract")
    if not isinstance(value.get("corpus_id"), str) or not _IDENTIFIER.fullmatch(value["corpus_id"]):
        issues.append("guided scoping acceptance corpus_id is invalid")
    if not isinstance(value.get("corpus_version"), str) or not _SEMVER.fullmatch(value["corpus_version"]):
        issues.append("guided scoping acceptance corpus_version is invalid")
    cases = value.get("cases")
    case_ids: list[Any] = []
    if not isinstance(cases, list) or not cases:
        issues.append("guided scoping cases must be a non-empty array")
    else:
        for case in cases:
            if not isinstance(case, dict) or set(case) != {"case_id", "data_classification", "intent", "workbook_map", "expected"}:
                issues.append("guided scoping case fields do not match the contract")
                continue
            case_ids.append(case.get("case_id"))
            if not isinstance(case.get("case_id"), str) or not _IDENTIFIER.fullmatch(case["case_id"]):
                issues.append("guided scoping case_id is invalid")
            if case.get("data_classification") not in {"synthetic", "anonymized"}:
                issues.append("guided scoping case data_classification is invalid")
            try:
                create_model_intent(case.get("intent"))
            except (TypeError, ValueError) as exc:
                issues.append(f"guided scoping case intent is invalid: {exc}")
            workbook_map = case.get("workbook_map")
            if workbook_map is not None:
                try:
                    derive_workbook_scope_evidence(workbook_map)
                except (TypeError, ValueError) as exc:
                    issues.append(f"guided scoping case workbook_map is invalid: {exc}")
            issues.extend(_validate_expected(case.get("expected")))
        if len(case_ids) != len(set(case_ids)):
            issues.append("guided scoping case IDs must be unique")
    reviews = value.get("practitioner_reviews")
    if not isinstance(reviews, list):
        issues.append("guided scoping practitioner_reviews must be an array")
    else:
        for review in reviews:
            issues.extend(validate_scoping_practitioner_review(review))
        review_cases = [review.get("case_id") for review in reviews if isinstance(review, dict)]
        if len(review_cases) != len(set(review_cases)):
            issues.append("guided scoping practitioner review case IDs must be unique")
        references = [review.get("evidence_reference") for review in reviews if isinstance(review, dict)]
        if len(references) != len(set(references)):
            issues.append("guided scoping practitioner review evidence references must be unique")
        if cases and not set(review_cases).issubset(set(case_ids)):
            issues.append("guided scoping practitioner review references an unknown case")
    return tuple(dict.fromkeys(issues))


def run_guided_scoping_acceptance_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    issues = validate_guided_scoping_acceptance_corpus(corpus)
    if issues:
        raise ValueError("invalid guided scoping acceptance corpus: " + "; ".join(issues))
    case_results = [_run_case(case) for case in corpus["cases"]]
    implementation_status = "passed" if all(item["status"] == "passed" for item in case_results) else "failed"
    result_by_case = {item["case_id"]: item for item in case_results}
    valid_reviews = {
        review["case_id"]: review
        for review in corpus["practitioner_reviews"]
        if review["case_sha256"] == result_by_case[review["case_id"]]["case_sha256"]
        and review["assessment_sha256"] == result_by_case[review["case_id"]]["assessment_sha256"]
    }
    if any(review["status"] == "rejected" for review in valid_reviews.values()):
        practitioner_status = "rejected"
    elif set(valid_reviews) == set(result_by_case) and all(review["status"] == "accepted" for review in valid_reviews.values()):
        practitioner_status = "accepted"
    else:
        practitioner_status = "pending"
    representative = all(case["data_classification"] == "anonymized" for case in corpus["cases"])
    production_status = "accepted" if implementation_status == "passed" and practitioner_status == "accepted" and representative else "not_accepted"
    blockers = []
    if implementation_status != "passed":
        blockers.append("guided_scoping_case_failure")
    if practitioner_status != "accepted":
        blockers.append("guided_scoping_practitioner_review_incomplete")
    if not representative:
        blockers.append("representative_anonymized_scope_corpus_missing")
    if len(valid_reviews) != len(corpus["practitioner_reviews"]):
        blockers.append("stale_practitioner_review_reference")
    provisional = {
        "contract_version": "guided-scoping-acceptance-result.v1",
        "corpus_id": corpus["corpus_id"],
        "corpus_version": corpus["corpus_version"],
        "corpus_sha256": digest(corpus),
        "implementation_status": implementation_status,
        "practitioner_status": practitioner_status,
        "production_status": production_status,
        "case_results": case_results,
        "review_references": sorted(review["evidence_reference"] for review in corpus["practitioner_reviews"]),
        "blockers": sorted(blockers),
    }
    sha = digest(provisional)
    return {**provisional, "acceptance_id": f"fmrsa_{sha[:24]}", "acceptance_sha256": sha}


def validate_guided_scoping_acceptance_result(value: Any, *, corpus: dict[str, Any] | None = None) -> tuple[str, ...]:
    expected = {"contract_version", "acceptance_id", "acceptance_sha256", "corpus_id", "corpus_version", "corpus_sha256", "implementation_status", "practitioner_status", "production_status", "case_results", "review_references", "blockers"}
    if not isinstance(value, dict) or value.get("contract_version") != "guided-scoping-acceptance-result.v1":
        return ("unsupported guided scoping acceptance result contract",)
    issues = []
    if set(value) != expected:
        issues.append("guided scoping acceptance result fields do not match the contract")
    if not isinstance(value.get("corpus_id"), str) or not _IDENTIFIER.fullmatch(value["corpus_id"]):
        issues.append("guided scoping acceptance result corpus_id is invalid")
    if not isinstance(value.get("corpus_version"), str) or not _SEMVER.fullmatch(value["corpus_version"]):
        issues.append("guided scoping acceptance result corpus_version is invalid")
    if not isinstance(value.get("corpus_sha256"), str) or not _HEX_64.fullmatch(value["corpus_sha256"]):
        issues.append("guided scoping acceptance result corpus hash is invalid")
    if value.get("implementation_status") not in {"passed", "failed"}:
        issues.append("guided scoping acceptance result implementation_status is invalid")
    if value.get("practitioner_status") not in {"pending", "accepted", "rejected"}:
        issues.append("guided scoping acceptance result practitioner_status is invalid")
    if value.get("production_status") not in {"not_accepted", "accepted"}:
        issues.append("guided scoping acceptance result production_status is invalid")
    case_results = value.get("case_results")
    if not isinstance(case_results, list) or not case_results:
        issues.append("guided scoping acceptance result case_results must be non-empty")
    else:
        for case_result in case_results:
            issues.extend(_validate_case_result(case_result))
        case_ids = [item.get("case_id") for item in case_results if isinstance(item, dict)]
        if len(case_ids) != len(set(case_ids)):
            issues.append("guided scoping acceptance result case IDs must be unique")
        expected_implementation = "passed" if all(isinstance(item, dict) and item.get("status") == "passed" for item in case_results) else "failed"
        if value.get("implementation_status") != expected_implementation:
            issues.append("guided scoping acceptance result implementation status does not match cases")
    for field in ("review_references", "blockers"):
        items = value.get(field)
        if not isinstance(items, list) or not all(isinstance(item, str) and item for item in items) or items != sorted(set(items)):
            issues.append(f"guided scoping acceptance result {field} must be sorted unique strings")
    if value.get("production_status") == "accepted":
        if value.get("implementation_status") != "passed" or value.get("practitioner_status") != "accepted":
            issues.append("guided scoping production acceptance requires implementation and practitioner acceptance")
        if isinstance(case_results, list) and any(not isinstance(item, dict) or item.get("data_classification") != "anonymized" for item in case_results):
            issues.append("guided scoping production acceptance requires anonymized cases")
    provisional = {key: item for key, item in value.items() if key not in {"acceptance_id", "acceptance_sha256"}}
    sha = digest(provisional)
    if value.get("acceptance_sha256") != sha or value.get("acceptance_id") != f"fmrsa_{sha[:24]}":
        issues.append("guided scoping acceptance result identity does not match canonical payload")
    if corpus is not None:
        try:
            if value != run_guided_scoping_acceptance_corpus(corpus):
                issues.append("guided scoping acceptance result does not match deterministic recomputation")
        except ValueError as exc:
            issues.append(str(exc))
    return tuple(dict.fromkeys(issues))


def _validate_case_result(value: Any) -> list[str]:
    expected = {"case_id", "case_sha256", "data_classification", "status", "assessment_id", "assessment_sha256", "state", "candidate_outcomes", "selected_family", "compiled_job_sha256", "issues"}
    if not isinstance(value, dict) or set(value) != expected:
        return ["guided scoping acceptance case result fields do not match the contract"]
    issues = []
    if not isinstance(value.get("case_id"), str) or not _IDENTIFIER.fullmatch(value["case_id"]):
        issues.append("guided scoping acceptance case result case_id is invalid")
    for field in ("case_sha256", "assessment_sha256"):
        if not isinstance(value.get(field), str) or not _HEX_64.fullmatch(value[field]):
            issues.append(f"guided scoping acceptance case result {field} is invalid")
    if not isinstance(value.get("assessment_id"), str) or not re.fullmatch(r"fmrs_[a-f0-9]{24}", value["assessment_id"]):
        issues.append("guided scoping acceptance case result assessment_id is invalid")
    if value.get("data_classification") not in {"synthetic", "anonymized"} or value.get("status") not in {"passed", "failed"} or value.get("state") not in _STATES:
        issues.append("guided scoping acceptance case result state is invalid")
    outcomes = value.get("candidate_outcomes")
    if not isinstance(outcomes, list) or any(not isinstance(item, dict) or set(item) != {"family_id", "suitability"} or not isinstance(item.get("family_id"), str) or item.get("suitability") not in _SUITABILITY for item in outcomes):
        issues.append("guided scoping acceptance candidate outcomes are invalid")
    elif outcomes != sorted(outcomes, key=lambda item: item["family_id"]):
        issues.append("guided scoping acceptance candidate outcomes must be ordered")
    if value.get("selected_family") is not None and not isinstance(value["selected_family"], str):
        issues.append("guided scoping acceptance selected_family is invalid")
    if value.get("compiled_job_sha256") is not None and (not isinstance(value["compiled_job_sha256"], str) or not _HEX_64.fullmatch(value["compiled_job_sha256"])):
        issues.append("guided scoping acceptance compiled job hash is invalid")
    result_issues = value.get("issues")
    if not isinstance(result_issues, list) or not all(isinstance(item, str) and item for item in result_issues) or result_issues != sorted(set(result_issues)):
        issues.append("guided scoping acceptance case issues must be sorted unique strings")
    return issues


def _validate_expected(value: Any) -> list[str]:
    if not isinstance(value, dict) or set(value) != {"state", "candidates", "required_questions", "selected_family"}:
        return ["guided scoping expected fields do not match the contract"]
    issues = []
    if value.get("state") not in _STATES:
        issues.append("guided scoping expected state is invalid")
    candidates = value.get("candidates")
    if not isinstance(candidates, list):
        issues.append("guided scoping expected candidates must be an array")
    else:
        for candidate in candidates:
            if not isinstance(candidate, dict) or set(candidate) != {"family_id", "suitability"} or not isinstance(candidate.get("family_id"), str) or candidate.get("suitability") not in _SUITABILITY:
                issues.append("guided scoping expected candidate is invalid")
        families = [item.get("family_id") for item in candidates if isinstance(item, dict)]
        if len(families) != len(set(families)):
            issues.append("guided scoping expected candidate families must be unique")
    questions = value.get("required_questions")
    if not isinstance(questions, list) or not all(isinstance(item, str) and item for item in questions) or len(questions) != len(set(questions)):
        issues.append("guided scoping required_questions must contain unique non-empty strings")
    selected = value.get("selected_family")
    if selected is not None and (not isinstance(selected, str) or selected not in {item.get("family_id") for item in candidates if isinstance(item, dict)}):
        issues.append("guided scoping selected_family must identify an expected candidate")
    return issues


def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    intent = create_model_intent(case["intent"])
    if case["workbook_map"] is not None:
        evidence = derive_workbook_scope_evidence(case["workbook_map"])
        intent = apply_workbook_scope_evidence(intent, evidence, workbook_map=case["workbook_map"])
    assessment = assess_model_intent(intent)
    expected = case["expected"]
    actual = {item["family_id"]: item["suitability"] for item in assessment["candidates"]}
    case_issues = []
    if assessment["state"] != expected["state"]:
        case_issues.append("assessment_state_mismatch")
    for candidate in expected["candidates"]:
        if actual.get(candidate["family_id"]) != candidate["suitability"]:
            case_issues.append(f"candidate_mismatch:{candidate['family_id']}")
    if not set(expected["required_questions"]).issubset(assessment["clarification_questions"]):
        case_issues.append("required_question_missing")
    selected = expected["selected_family"]
    job_sha256 = None
    if selected is not None:
        candidate = next((item for item in assessment["candidates"] if item["family_id"] == selected), None)
        if candidate is None or candidate["suitability"] not in {"eligible", "possible"}:
            case_issues.append("selected_family_not_selectable")
        else:
            confirmation = create_scope_confirmation(assessment, selected_family=selected, acknowledged_limitations=candidate["limitations"])
            job = compile_confirmed_scope(assessment, confirmation)
            if job["model_family"] != selected:
                case_issues.append("compiled_family_mismatch")
            job_sha256 = digest(job)
    return {
        "case_id": case["case_id"],
        "case_sha256": digest(case),
        "data_classification": case["data_classification"],
        "status": "passed" if not case_issues else "failed",
        "assessment_id": assessment["assessment_id"],
        "assessment_sha256": assessment["assessment_sha256"],
        "state": assessment["state"],
        "candidate_outcomes": [{"family_id": family, "suitability": actual[family]} for family in sorted(actual)],
        "selected_family": selected,
        "compiled_job_sha256": job_sha256,
        "issues": sorted(case_issues),
    }
