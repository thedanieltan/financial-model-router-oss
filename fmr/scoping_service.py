from __future__ import annotations

import re
from typing import Any

from fmr.core import ModelJob, create_model_intent, create_scope_assessment, create_scope_candidate
from fmr.core.scoping import validate_model_intent, validate_scope_assessment, validate_scope_confirmation
from fmr.knowledge import FamilyPlaybook, KnowledgeRegistry


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _raw_intent(intent: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in intent.items() if key not in {"contract_version", "intent_id", "intent_sha256"}}


def _canonical_intent(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("contract_version") == "model-intent.v1":
        issues = validate_model_intent(value)
        if issues:
            raise ValueError("invalid model intent: " + "; ".join(issues))
        return value
    return create_model_intent(value)


def answer_scope_question(intent: dict[str, Any], question_id: str, answer: str, *, knowledge: KnowledgeRegistry | None = None) -> dict[str, Any]:
    registry = knowledge or KnowledgeRegistry.builtins()
    canonical = _canonical_intent(intent)
    try:
        question = registry.question(question_id)
    except StopIteration as exc:
        raise ValueError("unknown scope question") from exc
    allowed = {item["value"] for item in question.options}
    if answer not in allowed:
        raise ValueError("answer is not an allowed question option")
    raw = _raw_intent(canonical)
    if question.intent_field == "decision_context":
        raw["decision_context"] = answer
    elif question.intent_field.startswith("context."):
        context = dict(raw.get("context", {}))
        context[question.intent_field.split(".", 1)[1]] = answer
        raw["context"] = context
    else:
        raise ValueError("scope question intent_field is unsupported")
    raw["unanswered_questions"] = [item for item in raw.get("unanswered_questions", []) if item != question_id]
    return create_model_intent(raw)


def assess_model_intent(intent: dict[str, Any], *, knowledge: KnowledgeRegistry | None = None) -> dict[str, Any]:
    registry = knowledge or KnowledgeRegistry.builtins()
    canonical = _canonical_intent(intent)
    contradictions = _contradictions(canonical)
    ranked: list[tuple[int, FamilyPlaybook, list[str], list[str], list[str], list[str]]] = []
    eliminated: list[dict[str, Any]] = []
    text = _normalize(" ".join((canonical["objective"], *canonical["requested_outcomes"])))
    for playbook in registry.playbooks:
        score, support, conflicts = _evidence(canonical, playbook, text)
        missing = [f"data:{item}" for item in playbook.required_data if item not in canonical["available_data"]]
        missing.extend(f"assumption:{item}" for item in playbook.required_assumptions if item not in canonical["available_assumptions"])
        unmet_prerequisites = _unmet_prerequisites(canonical, playbook)
        if score == 0:
            eliminated.append(_candidate(playbook, "unsupported", support, conflicts or ["intent does not match this family"], missing, unmet_prerequisites))
            continue
        ranked.append((score, playbook, support, conflicts, missing, unmet_prerequisites))
    ranked.sort(key=lambda item: (-item[0], item[1].family_id))
    candidates = []
    for _, playbook, support, conflicts, missing, prerequisites in ranked:
        suitability = "blocked" if prerequisites else ("possible" if missing or conflicts else "eligible")
        candidates.append(_candidate(playbook, suitability, support, conflicts, missing, prerequisites))
    questions = _questions(canonical, [item[1] for item in ranked], registry)
    if contradictions:
        state = "contradictory_requirements"
        questions = []
    elif canonical["decision_context"] == "unknown":
        state = "clarification_required"
        if "What decision should the model help you make?" not in questions:
            questions.insert(0, "What decision should the model help you make?")
    elif not candidates:
        state = "unsupported_scope"
        questions = []
    else:
        state = "candidate_scopes"
    if state == "clarification_required" and not questions:
        questions = ["What decision should the model help you make?"]
    if contradictions:
        eliminated = [_with_conflicts(item, contradictions) for item in eliminated]
        candidates = [_with_conflicts(item, contradictions) for item in candidates]
    return create_scope_assessment(
        intent=canonical,
        state=state,
        candidates=candidates,
        eliminated_candidates=eliminated,
        clarification_questions=questions,
        knowledge_base_version=f"{registry.version}+{registry.sha256[:12]}",
    )


def compile_confirmed_scope(assessment: dict[str, Any], confirmation: dict[str, Any], *, input_references: dict[str, Any] | None = None) -> dict[str, Any]:
    assessment_issues = validate_scope_assessment(assessment)
    if assessment_issues:
        raise ValueError("invalid scope assessment: " + "; ".join(assessment_issues))
    confirmation_issues = validate_scope_confirmation(confirmation)
    if confirmation_issues:
        raise ValueError("invalid scope confirmation: " + "; ".join(confirmation_issues))
    if confirmation["assessment_id"] != assessment["assessment_id"] or confirmation["assessment_sha256"] != assessment["assessment_sha256"]:
        raise ValueError("scope confirmation does not reference this assessment")
    if confirmation["knowledge_base_version"] != assessment["knowledge_base_version"]:
        raise ValueError("scope confirmation knowledge version does not match assessment")
    candidate = next((item for item in assessment["candidates"] if item["family_id"] == confirmation["selected_family"] and item["suitability"] in {"eligible", "possible"}), None)
    if candidate is None:
        raise ValueError("scope confirmation does not identify a selectable candidate")
    if not set(candidate["limitations"]).issubset(confirmation["acknowledged_limitations"]):
        raise ValueError("scope confirmation does not acknowledge every candidate limitation")
    intent = assessment["intent"]
    return ModelJob.from_mapping({
        "contract_version": "model-job.v2",
        "objective": intent["objective"],
        "requested_deliverables": candidate["deliverables"],
        "model_family": candidate["family_id"],
        "industry": intent["industry"],
        "context": intent["context"],
        "available_data": intent["available_data"],
        "available_assumptions": intent["available_assumptions"],
        "input_references": input_references or {},
        "existing_model": intent["existing_model"],
        "output_formats": intent["output_formats"],
        "constraints": intent["constraints"],
        "privacy_constraints": intent["privacy_constraints"],
        "licensing_constraints": intent["licensing_constraints"],
        "scope_confirmation": confirmation,
    }).to_dict()


def _evidence(intent: dict[str, Any], playbook: FamilyPlaybook, text: str) -> tuple[int, list[str], list[str]]:
    score, support, conflicts = 0, [], []
    decision = intent["decision_context"]
    if decision in playbook.decision_contexts:
        score += 4
        support.append(f"decision_context:{decision}")
    elif decision not in {"unknown", "other"}:
        conflicts.append(f"decision_context:{decision} is outside declared uses")
    for term in playbook.outcome_terms:
        if _normalize(term) in text:
            score += 2 + len(_normalize(term).split())
            support.append(f"outcome_term:{term}")
    context = intent["context"]
    if playbook.family_id == "three_statement" and context.get("linked_statements_needed") == "yes":
        score += 4
        support.append("answer:linked_statements_needed=yes")
    if playbook.family_id == "debt_capacity_refinancing":
        if context.get("debt_decision_needed") == "yes":
            score += 4
            support.append("answer:debt_decision_needed=yes")
        elif context.get("debt_decision_needed") == "no":
            conflicts.append("answer:debt_decision_needed=no")
    if playbook.family_id == "operating_company_dcf" and context.get("operating_forecast_available") == "yes":
        score += 2
        support.append("answer:operating_forecast_available=yes")
    if playbook.family_id == "three_statement" and decision in {"valuation", "acquisition"} and context.get("operating_forecast_available") == "no":
        score += 3
        support.append("prerequisite:operating forecast required before valuation")
    return score, sorted(set(support)), sorted(set(conflicts))


def _unmet_prerequisites(intent: dict[str, Any], playbook: FamilyPlaybook) -> list[str]:
    missing = []
    for prerequisite in playbook.prerequisites:
        if prerequisite == "supported_operating_forecast" and intent["context"].get("operating_forecast_available") != "yes":
            missing.append(prerequisite)
    return missing


def _candidate(playbook: FamilyPlaybook, suitability: str, support: list[str], conflicts: list[str], missing: list[str], prerequisites: list[str]) -> dict[str, Any]:
    return create_scope_candidate({
        "family_id": playbook.family_id,
        "title": playbook.title,
        "purpose": playbook.purpose,
        "suitability": suitability,
        "supporting_evidence": support,
        "conflicting_evidence": conflicts,
        "missing_information": missing,
        "limitations": list(playbook.limitations),
        "prerequisites": prerequisites,
        "deliverables": list(playbook.expected_outputs),
        "knowledge_references": [f"playbook:{playbook.playbook_id}@{playbook.version}", *(f"source:{item}" for item in playbook.source_references)],
    })


def _field_is_answered(intent: dict[str, Any], field: str) -> bool:
    if field == "decision_context":
        return intent["decision_context"] != "unknown"
    if field.startswith("context."):
        return field.split(".", 1)[1] in intent["context"]
    return False


def _questions(intent: dict[str, Any], playbooks: list[FamilyPlaybook], registry: KnowledgeRegistry) -> list[str]:
    ids = {question_id for playbook in playbooks for question_id in playbook.question_ids}
    questions = [registry.question(question_id).prompt for question_id in sorted(ids) if not _field_is_answered(intent, registry.question(question_id).intent_field)]
    return sorted(set(questions))


def _contradictions(intent: dict[str, Any]) -> list[str]:
    context = intent["context"]
    issues = []
    if context.get("forecast_horizon_known") == "no" and intent["planning_horizon"] is not None:
        issues.append("forecast horizon is both supplied and declared unknown")
    return issues


def _with_conflicts(candidate: dict[str, Any], conflicts: list[str]) -> dict[str, Any]:
    raw = {key: value for key, value in candidate.items() if key != "contract_version"}
    raw["suitability"] = "blocked" if candidate["suitability"] != "unsupported" else "unsupported"
    raw["conflicting_evidence"] = sorted(set((*candidate["conflicting_evidence"], *conflicts)))
    return create_scope_candidate(raw)
