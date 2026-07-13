from __future__ import annotations

import re

from fmr.model_specs import MODEL_DEFINITIONS
from fmr.readiness import assess_readiness
from fmr.types import ModelDefinition, ModelRequest, Recommendation


def normalize_objective(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def route_request(request: ModelRequest) -> Recommendation:
    normalized = normalize_objective(request.objective)
    scored: list[tuple[int, ModelDefinition, tuple[str, ...]]] = []
    for definition in MODEL_DEFINITIONS:
        matches = tuple(term for term in definition.objective_terms if term in normalized)
        score = sum(len(term.split()) for term in matches)
        scored.append((score, definition, matches))
    scored.sort(key=lambda item: (-item[0], item[1].model_family))
    score, definition, matches = scored[0]
    if score == 0:
        raise ValueError("objective does not match a supported model family; use budget, three-statement, DCF, or debt/refinancing language")
    readiness = assess_readiness(request, definition)
    confidence = "high" if score >= 2 else "medium"
    reasons = tuple([f"objective matched: {term}" for term in matches] + [f"role supplied: {request.role}"] + ["all required inputs are present" if readiness.ready else f"{len(readiness.blockers)} readiness blocker(s) remain"])
    return Recommendation(
        contract_version="model-recommendation.v1",
        model_family=definition.model_family,
        title=definition.title,
        confidence=confidence,
        reasons=reasons,
        readiness=readiness,
    )
