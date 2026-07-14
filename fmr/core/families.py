from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from fmr.core.jobs import ModelJob


@dataclass(frozen=True)
class ModelFamilyDefinition:
    family_id: str
    title: str
    analytical_objective: str
    required_deliverables: tuple[str, ...]
    required_data: tuple[str, ...]
    required_assumptions: tuple[str, ...]
    optional_inputs: tuple[str, ...]
    expected_checks: tuple[str, ...]
    supported_industry_extensions: tuple[str, ...]
    limitations: tuple[str, ...]
    classification_terms: tuple[str, ...]
    contract_version: str = "model-family-definition.v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "family_id": self.family_id,
            "title": self.title,
            "analytical_objective": self.analytical_objective,
            "required_deliverables": list(self.required_deliverables),
            "required_data": list(self.required_data),
            "required_assumptions": list(self.required_assumptions),
            "optional_inputs": list(self.optional_inputs),
            "expected_checks": list(self.expected_checks),
            "supported_industry_extensions": list(self.supported_industry_extensions),
            "limitations": list(self.limitations),
        }


FAMILIES: tuple[ModelFamilyDefinition, ...] = (
    ModelFamilyDefinition(
        "budget_forecast", "Budget and forecast", "Project operating performance, liquidity and funding needs.",
        ("budget_forecast",),
        ("income_statement_history", "revenue_drivers", "operating_cost_drivers"),
        ("forecast_horizon",), ("balance_sheet_history", "cash_flow_history"),
        ("period_continuity", "cash_reconciliation", "assumption_coverage"),
        ("saas", "logistics", "hospitality"), ("Not a valuation opinion.",),
        ("budget", "forecast", "financial plan", "runway"),
    ),
    ModelFamilyDefinition(
        "three_statement", "Integrated three-statement", "Produce linked income statement, balance sheet and cash-flow projections.",
        ("three_statement_forecast",),
        ("income_statement_history", "balance_sheet_history", "cash_flow_history", "capital_expenditure", "working_capital", "debt_schedule"),
        ("forecast_horizon", "tax_rate"), (),
        ("balance_sheet_balances", "cash_flow_reconciles", "retained_earnings_rolls_forward"),
        ("saas", "logistics", "hospitality"), ("Requires complete opening balances.",),
        ("three statement", "three-statement", "integrated statements", "integrated model"),
    ),
    ModelFamilyDefinition(
        "operating_company_dcf", "Operating-company DCF", "Estimate enterprise and equity value from operating cash flows.",
        ("operating_forecast", "enterprise_value", "equity_value"),
        ("income_statement_history", "cash_flow_history", "revenue_drivers", "capital_expenditure", "working_capital", "net_debt"),
        ("forecast_horizon", "tax_rate", "discount_rate", "terminal_value_assumption"),
        ("balance_sheet_history",),
        ("discount_factor_monotonicity", "terminal_value_reconciliation", "enterprise_equity_bridge"),
        ("saas", "logistics", "hospitality"), ("Not an investment recommendation.",),
        ("dcf", "discounted cash flow", "operating company valuation", "enterprise value"),
    ),
    ModelFamilyDefinition(
        "debt_capacity_refinancing", "Debt capacity and refinancing", "Assess debt service, leverage, liquidity and refinancing options.",
        ("debt_capacity", "refinancing_analysis"),
        ("income_statement_history", "cash_flow_history", "debt_schedule", "liquidity_position"),
        ("forecast_horizon", "interest_rate_assumption", "repayment_terms", "covenant_thresholds"), (),
        ("debt_roll_forward", "interest_reconciliation", "covenant_headroom", "liquidity_minimum"),
        ("saas", "logistics", "hospitality", "energy"), ("Does not constitute a lending decision.",),
        ("debt capacity", "refinancing", "refinance", "covenant", "leverage"),
    ),
)

FAMILY_BY_ID = {item.family_id: item for item in FAMILIES}


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def classify_job(job: ModelJob) -> dict[str, Any]:
    if job.model_family:
        if job.model_family not in FAMILY_BY_ID:
            return {"status": "unsupported_family", "selected_family": None, "candidates": [], "reasons": [f"explicit family is not registered: {job.model_family}"]}
        return {"status": "selected", "selected_family": job.model_family, "candidates": [job.model_family], "reasons": ["explicit model_family request"]}
    text = _normalize(" ".join((job.objective, *job.requested_deliverables)))
    scores: list[tuple[int, str, tuple[str, ...]]] = []
    for family in FAMILIES:
        matches = tuple(term for term in family.classification_terms if _normalize(term) in text)
        deliverables = set(job.requested_deliverables).intersection(family.required_deliverables)
        score = sum(len(_normalize(term).split()) for term in matches) + (3 * len(deliverables))
        scores.append((score, family.family_id, matches))
    best = max(score for score, _, _ in scores)
    if best == 0:
        return {"status": "unsupported_family", "selected_family": None, "candidates": [], "reasons": ["request does not match a registered model family"]}
    winners = sorted(family_id for score, family_id, _ in scores if score == best)
    if len(winners) > 1:
        return {"status": "ambiguous_family", "selected_family": None, "candidates": winners, "reasons": ["multiple model families have the same classification score"]}
    matches = next(matches for score, family_id, matches in scores if score == best and family_id == winners[0])
    return {"status": "selected", "selected_family": winners[0], "candidates": winners, "reasons": [f"matched: {term}" for term in matches] or ["requested deliverables matched"]}
