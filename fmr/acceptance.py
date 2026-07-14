from __future__ import annotations

import hashlib
import json
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fmr.core.receipts import validate_execution_result
from fmr.execution import ExecutionOrchestrator, SqliteExecutionLedger
from fmr.provider_service import prepare_handoff


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def validate_acceptance_corpus(value: dict[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(value, dict) or value.get("contract_version") != "model-acceptance-corpus.v1":
        return ("unsupported model acceptance corpus contract",)
    if set(value) != {"contract_version", "corpus_id", "cases", "practitioner_reviews"}:
        issues.append("acceptance corpus fields do not match the contract")
    if not isinstance(value.get("corpus_id"), str) or not value["corpus_id"]:
        issues.append("corpus_id is required")
    cases = value.get("cases")
    if not isinstance(cases, list) or not cases:
        issues.append("cases must be a non-empty array")
    else:
        identifiers = []
        for case in cases:
            if not isinstance(case, dict) or set(case) != {"case_id", "data_classification", "job", "canonical_input", "assertions"}:
                issues.append("acceptance case fields do not match the contract")
                continue
            identifiers.append(case.get("case_id"))
            if not isinstance(case.get("case_id"), str) or not case["case_id"]:
                issues.append("case_id is required")
            if case.get("data_classification") not in {"synthetic", "anonymized"}:
                issues.append("case data_classification is invalid")
            if not isinstance(case.get("job"), dict) or not isinstance(case.get("canonical_input"), dict):
                issues.append("case job and canonical_input must be objects")
            assertions = case.get("assertions")
            if not isinstance(assertions, list) or not assertions:
                issues.append("case assertions must be a non-empty array")
            elif any(not _valid_assertion(item) for item in assertions):
                issues.append("case assertion is invalid")
        if len(identifiers) != len(set(identifiers)):
            issues.append("case IDs must be unique")
    reviews = value.get("practitioner_reviews")
    if not isinstance(reviews, list) or any(not _valid_review(item) for item in reviews):
        issues.append("practitioner reviews are invalid")
    return tuple(dict.fromkeys(issues))


def run_acceptance_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    issues = validate_acceptance_corpus(corpus)
    if issues:
        raise ValueError("invalid acceptance corpus: " + "; ".join(issues))
    case_results = [_run_case(case) for case in corpus["cases"]]
    implementation_status = "passed" if all(item["status"] == "passed" for item in case_results) else "failed"
    families = {case["job"].get("model_family") for case in corpus["cases"]}
    accepted_families = {review["model_family"] for review in corpus["practitioner_reviews"] if review["status"] == "accepted"}
    rejected = any(review["status"] == "rejected" for review in corpus["practitioner_reviews"])
    if rejected:
        practitioner_status = "rejected"
    elif families and families.issubset(accepted_families):
        practitioner_status = "accepted"
    else:
        practitioner_status = "pending"
    production_status = "accepted" if implementation_status == "passed" and practitioner_status == "accepted" and any(case["data_classification"] == "anonymized" for case in corpus["cases"]) else "not_accepted"
    blockers = []
    if implementation_status != "passed":
        blockers.append("acceptance_case_failure")
    if practitioner_status != "accepted":
        blockers.append("practitioner_review_incomplete")
    if not any(case["data_classification"] == "anonymized" for case in corpus["cases"]):
        blockers.append("representative_anonymized_case_missing")
    provisional = {"contract_version": "model-acceptance-result.v1", "corpus_id": corpus["corpus_id"], "corpus_sha256": _digest(corpus), "implementation_status": implementation_status, "practitioner_status": practitioner_status, "production_status": production_status, "case_results": case_results, "review_references": sorted(review["evidence_reference"] for review in corpus["practitioner_reviews"]), "blockers": sorted(blockers)}
    return {**provisional, "acceptance_id": f"fmra_{_digest(provisional)[:24]}"}


def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "canonical.json"
        source.write_text(json.dumps(case["canonical_input"], sort_keys=True), encoding="utf-8")
        job = json.loads(json.dumps(case["job"]))
        job["input_references"] = {"canonical_financial_data": {"contract_version": "canonical-financial-data.v2", "path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}}
        constraints = dict(job.get("constraints", {}))
        constraints["allowed_providers"] = ["python-forecast"]
        job["constraints"] = constraints
        handoff = prepare_handoff(job)
        orchestrator = ExecutionOrchestrator(ledger=SqliteExecutionLedger(root / "ledger.sqlite3"), managed_output_root=root / "outputs")
        execution = orchestrator.execute_request({"contract_version": "execution-request.v1", "handoff": handoff, "idempotency_key": case["case_id"], "execution_mode": "local", "timeout_seconds": 30, "secret_references": [], "output_policy": {"mode": "managed", "overwrite": False, "publish": False}})
        validation = validate_execution_result(execution, handoff=handoff)
        json_artifacts = [item for item in execution.get("output_artifact_references", []) if item.get("format") == "json"]
        output = json.loads(Path(json_artifacts[0]["path"]).read_text(encoding="utf-8")) if len(json_artifacts) == 1 else {}
        assertions = [{"assertion_id": item["assertion_id"], "status": "passed" if _assert(output, item) else "failed"} for item in case["assertions"]]
        passed = execution.get("state") == "completed" and not validation and all(item["status"] == "passed" for item in assertions)
        return {"case_id": case["case_id"], "case_sha256": _digest(case), "data_classification": case["data_classification"], "model_family": job.get("model_family"), "provider_id": handoff["provider"]["provider_id"], "provider_version": handoff["provider"]["version"], "package_id": handoff["package"]["package_id"], "package_version": handoff["package"]["version"], "status": "passed" if passed else "failed", "assertions": assertions}


def _assert(output: dict[str, Any], assertion: dict[str, Any]) -> bool:
    try:
        actual = _resolve(output, assertion["path"])
        expected = assertion["expected"]
        operator = assertion["operator"]
        if operator == "equals":
            return actual == expected
        left, right = Decimal(str(actual)), Decimal(str(expected))
        if operator == "approximately_equals":
            return abs(left - right) <= Decimal(str(assertion.get("tolerance", "0")))
        if operator == "greater_than_or_equal":
            return left >= right
        if operator == "less_than_or_equal":
            return left <= right
    except (KeyError, IndexError, InvalidOperation, TypeError, ValueError):
        return False
    return False


def _resolve(value: Any, path: str) -> Any:
    current = value
    for token in path.strip("/").split("/"):
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def _valid_assertion(item: Any) -> bool:
    return isinstance(item, dict) and set(item) in ({"assertion_id", "path", "operator", "expected"}, {"assertion_id", "path", "operator", "expected", "tolerance"}) and isinstance(item.get("assertion_id"), str) and isinstance(item.get("path"), str) and item.get("operator") in {"equals", "approximately_equals", "greater_than_or_equal", "less_than_or_equal"}


def _valid_review(item: Any) -> bool:
    return isinstance(item, dict) and set(item) == {"model_family", "reviewer_role", "status", "evidence_reference"} and all(isinstance(item.get(key), str) and item[key] for key in ("model_family", "reviewer_role", "evidence_reference")) and item.get("status") in {"accepted", "rejected"}
