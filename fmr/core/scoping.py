from __future__ import annotations

from typing import Any

from fmr.core.handoffs import digest


DECISION_CONTEXTS = (
    "acquisition",
    "financing",
    "liquidity",
    "operating_plan",
    "other",
    "refinancing",
    "unknown",
    "valuation",
)
ASSESSMENT_STATES = (
    "collecting_intent",
    "clarification_required",
    "candidate_scopes",
    "scope_confirmed",
    "unsupported_scope",
    "contradictory_requirements",
)
SUITABILITY_STATES = ("eligible", "possible", "blocked", "unsupported")


def _strings(value: Any, field: str, *, required: bool = False) -> list[str]:
    if value is None:
        value = []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field} must be an array of non-empty strings")
    cleaned = sorted(item.strip() for item in value)
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{field} must not contain duplicates")
    if required and not cleaned:
        raise ValueError(f"{field} must contain at least one item")
    return cleaned


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return dict(value)


def create_model_intent(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("model intent must be an object")
    allowed = {
        "objective", "decision_context", "requested_outcomes", "planning_horizon",
        "industry", "context", "available_data", "available_assumptions",
        "existing_model", "output_formats", "constraints", "privacy_constraints",
        "licensing_constraints", "unanswered_questions",
    }
    if set(value) - allowed:
        raise ValueError("model intent contains unsupported fields")
    objective = value.get("objective")
    if not isinstance(objective, str) or not objective.strip():
        raise ValueError("objective must be a non-empty string")
    decision_context = value.get("decision_context", "unknown")
    if decision_context not in DECISION_CONTEXTS:
        raise ValueError("decision_context is not supported")
    industry = value.get("industry")
    if industry is not None and (not isinstance(industry, str) or not industry.strip()):
        raise ValueError("industry must be a non-empty string when supplied")
    horizon = value.get("planning_horizon")
    if horizon is not None:
        if not isinstance(horizon, dict) or set(horizon) != {"value", "unit"}:
            raise ValueError("planning_horizon must contain value and unit")
        if isinstance(horizon.get("value"), bool) or not isinstance(horizon.get("value"), int) or horizon["value"] < 1:
            raise ValueError("planning_horizon.value must be a positive integer")
        if horizon.get("unit") not in {"months", "years", "periods"}:
            raise ValueError("planning_horizon.unit is not supported")
    provisional = {
        "contract_version": "model-intent.v1",
        "objective": objective.strip(),
        "decision_context": decision_context,
        "requested_outcomes": _strings(value.get("requested_outcomes"), "requested_outcomes"),
        "planning_horizon": horizon,
        "industry": industry.strip() if industry else None,
        "context": _mapping(value.get("context"), "context"),
        "available_data": _strings(value.get("available_data"), "available_data"),
        "available_assumptions": _strings(value.get("available_assumptions"), "available_assumptions"),
        "existing_model": _mapping(value.get("existing_model"), "existing_model"),
        "output_formats": _strings(value.get("output_formats") or ["json"], "output_formats", required=True),
        "constraints": _mapping(value.get("constraints"), "constraints"),
        "privacy_constraints": _strings(value.get("privacy_constraints"), "privacy_constraints"),
        "licensing_constraints": _strings(value.get("licensing_constraints"), "licensing_constraints"),
        "unanswered_questions": _strings(value.get("unanswered_questions"), "unanswered_questions"),
    }
    sha = digest(provisional)
    return {**provisional, "intent_id": f"fmri_{sha[:24]}", "intent_sha256": sha}


def validate_model_intent(value: Any) -> tuple[str, ...]:
    if not isinstance(value, dict) or value.get("contract_version") != "model-intent.v1":
        return ("unsupported model intent contract",)
    expected = {
        "contract_version", "intent_id", "intent_sha256", "objective", "decision_context",
        "requested_outcomes", "planning_horizon", "industry", "context", "available_data",
        "available_assumptions", "existing_model", "output_formats", "constraints",
        "privacy_constraints", "licensing_constraints", "unanswered_questions",
    }
    issues: list[str] = []
    if set(value) != expected:
        issues.append("model intent fields do not match the contract")
    provisional = {key: item for key, item in value.items() if key not in {"intent_id", "intent_sha256"}}
    sha = digest(provisional)
    if value.get("intent_sha256") != sha or value.get("intent_id") != f"fmri_{sha[:24]}":
        issues.append("model intent identity does not match canonical payload")
    try:
        rebuilt = create_model_intent({key: item for key, item in provisional.items() if key != "contract_version"})
        if rebuilt != value:
            issues.append("model intent does not match normalized payload")
    except ValueError as exc:
        issues.append(str(exc))
    return tuple(dict.fromkeys(issues))


def create_scope_candidate(value: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "family_id", "title", "purpose", "suitability", "supporting_evidence",
        "conflicting_evidence", "missing_information", "limitations", "prerequisites",
        "deliverables", "knowledge_references",
    }
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError("scope candidate contains unsupported fields")
    for field in ("family_id", "title", "purpose"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
    if value.get("suitability") not in SUITABILITY_STATES:
        raise ValueError("scope candidate suitability is not supported")
    return {
        "contract_version": "model-scope-candidate.v1",
        "family_id": value["family_id"].strip(),
        "title": value["title"].strip(),
        "purpose": value["purpose"].strip(),
        "suitability": value["suitability"],
        "supporting_evidence": _strings(value.get("supporting_evidence"), "supporting_evidence"),
        "conflicting_evidence": _strings(value.get("conflicting_evidence"), "conflicting_evidence"),
        "missing_information": _strings(value.get("missing_information"), "missing_information"),
        "limitations": _strings(value.get("limitations"), "limitations"),
        "prerequisites": _strings(value.get("prerequisites"), "prerequisites"),
        "deliverables": _strings(value.get("deliverables"), "deliverables", required=True),
        "knowledge_references": _strings(value.get("knowledge_references"), "knowledge_references", required=True),
    }


def validate_scope_candidate(value: Any) -> tuple[str, ...]:
    if not isinstance(value, dict) or value.get("contract_version") != "model-scope-candidate.v1":
        return ("unsupported scope candidate contract",)
    try:
        rebuilt = create_scope_candidate({key: item for key, item in value.items() if key != "contract_version"})
        return () if rebuilt == value else ("scope candidate does not match normalized payload",)
    except ValueError as exc:
        return (str(exc),)


def create_scope_assessment(*, intent: dict[str, Any], state: str, candidates: list[dict[str, Any]], eliminated_candidates: list[dict[str, Any]] | None = None, clarification_questions: list[str] | None = None, confirmed_family: str | None = None, knowledge_base_version: str) -> dict[str, Any]:
    intent_issues = validate_model_intent(intent)
    if intent_issues:
        raise ValueError("invalid model intent: " + "; ".join(intent_issues))
    if state not in ASSESSMENT_STATES:
        raise ValueError("assessment state is not supported")
    normalized_candidates = [create_scope_candidate({key: item for key, item in candidate.items() if key != "contract_version"}) for candidate in candidates]
    normalized_eliminated = [create_scope_candidate({key: item for key, item in candidate.items() if key != "contract_version"}) for candidate in (eliminated_candidates or [])]
    family_ids = [item["family_id"] for item in (*normalized_candidates, *normalized_eliminated)]
    if len(family_ids) != len(set(family_ids)):
        raise ValueError("assessment family IDs must be unique")
    questions = _strings(clarification_questions, "clarification_questions")
    if state == "clarification_required" and not questions:
        raise ValueError("clarification_required assessment needs questions")
    if state == "scope_confirmed":
        if confirmed_family not in {item["family_id"] for item in normalized_candidates if item["suitability"] in {"eligible", "possible"}}:
            raise ValueError("confirmed_family must identify a selectable candidate")
    elif confirmed_family is not None:
        raise ValueError("confirmed_family is allowed only for scope_confirmed")
    if not isinstance(knowledge_base_version, str) or not knowledge_base_version.strip():
        raise ValueError("knowledge_base_version is required")
    provisional = {
        "contract_version": "model-scope-assessment.v1",
        "intent": intent,
        "state": state,
        "candidates": normalized_candidates,
        "eliminated_candidates": normalized_eliminated,
        "clarification_questions": questions,
        "confirmed_family": confirmed_family,
        "knowledge_base_version": knowledge_base_version.strip(),
    }
    sha = digest(provisional)
    return {**provisional, "assessment_id": f"fmrs_{sha[:24]}", "assessment_sha256": sha}


def validate_scope_assessment(value: Any) -> tuple[str, ...]:
    if not isinstance(value, dict) or value.get("contract_version") != "model-scope-assessment.v1":
        return ("unsupported scope assessment contract",)
    expected = {"contract_version", "assessment_id", "assessment_sha256", "intent", "state", "candidates", "eliminated_candidates", "clarification_questions", "confirmed_family", "knowledge_base_version"}
    issues: list[str] = []
    if set(value) != expected:
        issues.append("scope assessment fields do not match the contract")
    provisional = {key: item for key, item in value.items() if key not in {"assessment_id", "assessment_sha256"}}
    sha = digest(provisional)
    if value.get("assessment_sha256") != sha or value.get("assessment_id") != f"fmrs_{sha[:24]}":
        issues.append("scope assessment identity does not match canonical payload")
    try:
        rebuilt = create_scope_assessment(
            intent=value.get("intent"), state=value.get("state"), candidates=value.get("candidates", []),
            eliminated_candidates=value.get("eliminated_candidates", []), clarification_questions=value.get("clarification_questions", []),
            confirmed_family=value.get("confirmed_family"), knowledge_base_version=value.get("knowledge_base_version"),
        )
        if rebuilt != value:
            issues.append("scope assessment does not match deterministic recomputation")
    except (TypeError, ValueError) as exc:
        issues.append(str(exc))
    return tuple(dict.fromkeys(issues))


def create_scope_confirmation(assessment: dict[str, Any], *, selected_family: str, acknowledged_limitations: list[str]) -> dict[str, Any]:
    issues = validate_scope_assessment(assessment)
    if issues:
        raise ValueError("invalid scope assessment: " + "; ".join(issues))
    selectable = {item["family_id"]: item for item in assessment["candidates"] if item["suitability"] in {"eligible", "possible"}}
    if assessment["state"] not in {"candidate_scopes", "scope_confirmed"} or selected_family not in selectable:
        raise ValueError("selected family is not a selectable scope candidate")
    required = set(selectable[selected_family]["limitations"])
    acknowledged = set(_strings(acknowledged_limitations, "acknowledged_limitations"))
    if not required.issubset(acknowledged):
        raise ValueError("every candidate limitation must be acknowledged")
    provisional = {
        "contract_version": "scope-confirmation.v1",
        "assessment_id": assessment["assessment_id"],
        "assessment_sha256": assessment["assessment_sha256"],
        "selected_family": selected_family,
        "acknowledged_limitations": sorted(acknowledged),
        "confirmation_method": "explicit_user_confirmation",
        "knowledge_base_version": assessment["knowledge_base_version"],
    }
    sha = digest(provisional)
    return {**provisional, "confirmation_id": f"fmrc_{sha[:24]}", "confirmation_sha256": sha}


def validate_scope_confirmation(value: Any) -> tuple[str, ...]:
    if not isinstance(value, dict) or value.get("contract_version") != "scope-confirmation.v1":
        return ("unsupported scope confirmation contract",)
    expected = {"contract_version", "confirmation_id", "confirmation_sha256", "assessment_id", "assessment_sha256", "selected_family", "acknowledged_limitations", "confirmation_method", "knowledge_base_version"}
    issues: list[str] = []
    if set(value) != expected:
        issues.append("scope confirmation fields do not match the contract")
    provisional = {key: item for key, item in value.items() if key not in {"confirmation_id", "confirmation_sha256"}}
    sha = digest(provisional)
    if value.get("confirmation_sha256") != sha or value.get("confirmation_id") != f"fmrc_{sha[:24]}":
        issues.append("scope confirmation identity does not match canonical payload")
    if value.get("confirmation_method") != "explicit_user_confirmation":
        issues.append("scope confirmation method is not supported")
    try:
        _strings(value.get("acknowledged_limitations"), "acknowledged_limitations")
    except ValueError as exc:
        issues.append(str(exc))
    return tuple(dict.fromkeys(issues))
