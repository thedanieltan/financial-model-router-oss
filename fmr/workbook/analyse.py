from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fmr.plan import build_plan
from fmr.router import route_request
from fmr.types import ModelRequest, Recommendation, TransformationPlan
from fmr.workbook.evidence import WorkbookEvidence, derive_workbook_evidence
from fmr.workbook.types import WorkbookMap


@dataclass(frozen=True)
class WorkbookAnalysis:
    workbook_map: WorkbookMap
    original_request: ModelRequest
    effective_request: ModelRequest
    derived_evidence: WorkbookEvidence
    recommendation: Recommendation
    transformation_plan: TransformationPlan

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": "workbook-analysis.v1",
            "workbook_map": self.workbook_map.to_dict(),
            "original_request": self.original_request.to_dict(),
            "derived_evidence": self.derived_evidence.to_dict(),
            "effective_request": self.effective_request.to_dict(),
            "recommendation": self.recommendation.to_dict(),
            "transformation_plan": self.transformation_plan.to_dict(),
        }


def analyse_workbook_map(
    workbook_map: WorkbookMap,
    request: ModelRequest,
) -> WorkbookAnalysis:
    evidence = derive_workbook_evidence(workbook_map)
    effective = ModelRequest(
        objective=request.objective,
        role=request.role,
        available_data=tuple(
            sorted(set(request.available_data).union(evidence.available_data))
        ),
        workbook_capabilities=tuple(
            sorted(
                set(request.workbook_capabilities).union(
                    evidence.workbook_capabilities
                )
            )
        ),
        assumptions=request.assumptions,
    )
    recommendation = route_request(effective)
    plan = build_plan(effective)
    return WorkbookAnalysis(
        workbook_map=workbook_map,
        original_request=request,
        effective_request=effective,
        derived_evidence=evidence,
        recommendation=recommendation,
        transformation_plan=plan,
    )
