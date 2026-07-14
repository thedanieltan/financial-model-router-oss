from __future__ import annotations

import re
from typing import Any

from fmr.providers.native_xlsx.workbook.types import Classification

_PERIOD_RE = re.compile(
    r"^(?:fy\s*)?(?:19|20)\d{2}(?:\s*(?:a|e|f|actual|estimate|budget|forecast))?$",
    re.IGNORECASE,
)

_ROLE_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "income_statement": {
        "names": ("income statement", "profit and loss", "p&l", "pnl"),
        "metrics": ("revenue", "sales", "cost of sales", "gross profit", "operating profit", "ebitda", "ebit", "net income"),
    },
    "balance_sheet": {
        "names": ("balance sheet", "statement of financial position"),
        "metrics": ("assets", "liabilities", "equity", "cash", "inventory", "accounts receivable", "accounts payable", "debt"),
    },
    "cash_flow_statement": {
        "names": ("cash flow", "cashflow", "statement of cash flows"),
        "metrics": ("operating cash flow", "investing activities", "financing activities", "capital expenditure", "capex", "net change in cash"),
    },
    "assumptions": {
        "names": ("assumptions", "drivers", "inputs"),
        "metrics": ("growth rate", "tax rate", "discount rate", "wacc", "terminal growth", "forecast horizon"),
    },
    "debt_schedule": {
        "names": ("debt schedule", "borrowings", "loans"),
        "metrics": ("opening balance", "principal repayment", "interest expense", "maturity", "leverage", "covenant"),
    },
    "valuation": {
        "names": ("dcf", "valuation", "discounted cash flow"),
        "metrics": ("free cash flow", "discount factor", "terminal value", "enterprise value", "equity value", "wacc"),
    },
}

_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "revenue": ("revenue", "sales", "turnover"),
    "gross_profit": ("gross profit",),
    "ebitda": ("ebitda",),
    "operating_profit": ("operating profit", "ebit"),
    "net_income": ("net income", "net profit", "profit after tax"),
    "cash": ("cash", "cash and cash equivalents"),
    "debt": ("debt", "borrowings", "loans"),
    "total_assets": ("total assets",),
    "total_liabilities": ("total liabilities",),
    "equity": ("total equity", "shareholders equity", "equity"),
    "operating_cash_flow": ("operating cash flow", "cash from operations"),
    "capital_expenditure": ("capital expenditure", "capex"),
    "free_cash_flow": ("free cash flow",),
    "wacc": ("wacc", "discount rate"),
    "terminal_value": ("terminal value",),
}


def normalise_label(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9&]+", " ", value.lower()).split())


def detect_periods(rows: list[list[Any]]) -> tuple[str, ...]:
    periods: list[str] = []
    for row in rows[:20]:
        for value in row[:100]:
            text: str | None = None
            if isinstance(value, int) and 1900 <= value <= 2100:
                text = str(value)
            elif isinstance(value, str):
                candidate = " ".join(value.strip().split())
                if _PERIOD_RE.match(candidate) or candidate.lower() in {"actual", "budget", "forecast", "ltm", "ntm"}:
                    text = candidate
            if text and text not in periods:
                periods.append(text)
    return tuple(periods)


def detect_metrics(labels: list[str]) -> tuple[str, ...]:
    normalised_labels = [normalise_label(label) for label in labels]
    return tuple(
        metric
        for metric, aliases in _METRIC_ALIASES.items()
        if any(any(alias in label for alias in aliases) for label in normalised_labels)
    )


def classify_sheet(sheet_name: str, labels: list[str]) -> Classification:
    normalised_name = normalise_label(sheet_name)
    normalised_labels = [normalise_label(label) for label in labels]
    scored: list[tuple[int, str, tuple[str, ...]]] = []
    for role, rules in _ROLE_RULES.items():
        evidence: list[str] = []
        score = 0
        for term in rules["names"]:
            if term in normalised_name:
                score += 5
                evidence.append(f"sheet name matched: {term}")
        for term in rules["metrics"]:
            if any(term in label for label in normalised_labels):
                score += 1
                evidence.append(f"row label matched: {term}")
        scored.append((score, role, tuple(evidence)))
    scored.sort(key=lambda item: (-item[0], item[1]))
    best_score, best_role, evidence = scored[0]
    ties = [item for item in scored if item[0] == best_score and best_score > 0]
    if best_score == 0:
        return Classification("unknown", "low", ("no deterministic sheet-role rule matched",))
    if len(ties) > 1:
        roles = ", ".join(item[1] for item in ties)
        return Classification("unknown", "low", (f"ambiguous role scores: {roles}",))
    confidence = "high" if best_score >= 6 else "medium" if best_score >= 3 else "low"
    return Classification(best_role, confidence, evidence)
