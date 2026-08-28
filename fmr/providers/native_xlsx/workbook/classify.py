from __future__ import annotations

import re
from typing import Any

from fmr.providers.native_xlsx.workbook.types import Classification

_YEAR_TOKEN = r"(?:19|20)\d{2}"
_MONTH_TOKEN = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_PERIOD_RE = re.compile(
    rf"^(?:(?:fy\s*)?{_YEAR_TOKEN}(?:\s*(?:a|e|f|actual|estimate|budget|forecast))?|"
    rf"{_YEAR_TOKEN}[-/]?(?:0?[1-9]|1[0-2])(?:\s*(?:a|e|f|actual|estimate|budget|forecast))?|"
    rf"{_MONTH_TOKEN}[\s\-/']*(?:{_YEAR_TOKEN}|\d{{2}})(?:\s*(?:a|e|f|actual|estimate|budget|forecast))?|"
    rf"(?:q[1-4]\s*{_YEAR_TOKEN}|[1-4]q\s*(?:{_YEAR_TOKEN}|\d{{2}}))(?:\s*(?:a|e|f|actual|estimate|budget|forecast))?)$",
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
    "budget_forecast": {
        "names": ("budget", "forecast", "plan", "rolling forecast"),
        "metrics": ("budget", "forecast", "actual", "variance", "revenue", "operating costs"),
    },
    "assumptions": {
        "names": ("assumptions", "drivers", "inputs"),
        "metrics": ("growth rate", "tax rate", "discount rate", "wacc", "terminal growth", "forecast horizon"),
    },
    "headcount_schedule": {
        "names": ("headcount", "head count", "workforce", "hc plan", "people plan", "staffing"),
        "metrics": ("headcount", "fte", "salary", "payroll", "new hires", "hires", "employees"),
    },
    "revenue_schedule": {
        "names": ("revenue schedule", "sales plan", "sales forecast", "sales drivers", "revenue build", "revenue drivers"),
        "metrics": ("customers", "units", "volume", "price", "arr", "mrr", "churn", "bookings"),
    },
    "capex_schedule": {
        "names": ("capex", "capital expenditure", "fixed assets", "ppe", "pp&e"),
        "metrics": ("capital expenditure", "capex", "depreciation", "opening ppe", "closing ppe"),
    },
    "working_capital_schedule": {
        "names": ("working capital", "nwc"),
        "metrics": ("accounts receivable", "accounts payable", "inventory", "dso", "dpo", "dio"),
    },
    "debt_schedule": {
        "names": ("debt schedule", "borrowings", "loans"),
        "metrics": ("opening balance", "principal repayment", "interest expense", "maturity", "leverage", "covenant"),
    },
    "valuation": {
        "names": ("dcf", "valuation", "discounted cash flow"),
        "metrics": ("free cash flow", "discount factor", "terminal value", "enterprise value", "equity value", "wacc"),
    },
    "management_summary": {
        "names": ("management summary", "management report", "dashboard", "executive summary", "board pack", "kpi summary"),
        "metrics": ("revenue", "ebitda", "cash", "variance", "forecast", "kpi"),
    },
}

_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "revenue": ("revenue", "sales", "turnover", "net sales"),
    "operating_costs": ("operating costs", "operating expenses", "opex", "operating expense"),
    "cost_of_sales": ("cost of sales", "cost of goods sold", "cogs"),
    "gross_profit": ("gross profit",),
    "gross_margin": ("gross margin", "gross margin %"),
    "ebitda": ("ebitda",),
    "operating_profit": ("operating profit", "ebit"),
    "net_income": ("net income", "net profit", "profit after tax", "pat"),
    "tax_expense": ("tax expense", "income tax", "taxation"),
    "cash": ("cash", "cash and cash equivalents", "cash balance"),
    "accounts_receivable": ("accounts receivable", "trade receivables", "receivables", "ar"),
    "inventory": ("inventory", "inventories"),
    "accounts_payable": ("accounts payable", "trade payables", "payables", "ap"),
    "debt": ("debt", "borrowings", "loans", "total debt"),
    "total_assets": ("total assets",),
    "total_liabilities": ("total liabilities",),
    "equity": ("total equity", "shareholders equity", "shareholders' equity", "equity"),
    "operating_cash_flow": ("operating cash flow", "cash from operations", "cash flow from operations"),
    "capital_expenditure": ("capital expenditure", "capex"),
    "depreciation": ("depreciation", "depreciation expense"),
    "free_cash_flow": ("free cash flow", "fcf"),
    "headcount": ("headcount", "head count", "employees", "employee count", "fte", "ftes"),
    "payroll": ("payroll", "salary cost", "salaries", "wages", "people cost", "personnel cost"),
    "new_hires": ("new hires", "hires", "planned hires"),
    "customers": ("customers", "customer count", "active customers"),
    "volume": ("volume", "units", "units sold", "sales volume"),
    "price": ("price", "average selling price", "asp"),
    "arr": ("arr", "annual recurring revenue"),
    "mrr": ("mrr", "monthly recurring revenue"),
    "churn": ("churn", "churn rate", "customer churn"),
    "bookings": ("bookings", "new bookings"),
    "interest_expense": ("interest expense", "interest"),
    "principal_repayment": ("principal repayment", "debt repayment", "repayment"),
    "wacc": ("wacc", "discount rate"),
    "terminal_value": ("terminal value",),
    "enterprise_value": ("enterprise value", "ev"),
    "equity_value": ("equity value",),
}


def normalise_label(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9&%]+", " ", value.lower()).split())


def is_period_label(value: Any) -> bool:
    if isinstance(value, int) and 1900 <= value <= 2100:
        return True
    if not isinstance(value, str):
        return False
    candidate = " ".join(value.strip().split())
    return bool(_PERIOD_RE.fullmatch(candidate)) or candidate.lower() in {
        "actual",
        "budget",
        "forecast",
        "estimate",
        "ltm",
        "ntm",
    }


def classify_period_label(value: Any) -> Classification:
    if not is_period_label(value):
        return Classification("unknown", "low", ("not a recognized period label",))
    text = str(value).strip().lower()
    if re.search(r"(?:\bactual\b|(?:19|20)\d{2}\s*a\b)", text) or text == "actual":
        return Classification("actual", "high", ("explicit actual marker",))
    if re.search(r"(?:\bbudget\b|\bplan\b)", text) or text == "budget":
        return Classification("budget", "high", ("explicit budget marker",))
    if re.search(r"(?:\bforecast\b|\bestimate\b|\bntm\b|(?:19|20)\d{2}\s*[ef]\b)", text) or text in {"forecast", "estimate", "ntm"}:
        return Classification("forecast", "high", ("explicit forecast or estimate marker",))
    if text == "ltm":
        return Classification("actual", "medium", ("LTM treated as historical evidence",))
    return Classification("unspecified", "medium", ("recognized period without actual/budget/forecast marker",))


def detect_periods(rows: list[list[Any]]) -> tuple[str, ...]:
    periods: list[str] = []
    for row in rows[:50]:
        for value in row[:200]:
            if is_period_label(value):
                text = str(value) if not isinstance(value, str) else " ".join(value.strip().split())
                if text not in periods:
                    periods.append(text)
    return tuple(periods)


def classify_metric_label(label: str) -> Classification:
    normalized = normalise_label(label)
    if not normalized:
        return Classification("unknown", "low", ("empty label",))
    exact: list[tuple[str, str]] = []
    contained: list[tuple[int, str, str]] = []
    for metric, aliases in _METRIC_ALIASES.items():
        for alias in aliases:
            normalized_alias = normalise_label(alias)
            if normalized == normalized_alias:
                exact.append((metric, alias))
            elif normalized_alias and re.search(rf"(?:^|\s){re.escape(normalized_alias)}(?:$|\s)", normalized):
                contained.append((len(normalized_alias), metric, alias))
    if exact:
        metrics = sorted({metric for metric, _ in exact})
        if len(metrics) == 1:
            aliases = sorted({alias for metric, alias in exact if metric == metrics[0]})
            return Classification(metrics[0], "high", tuple(f"exact metric alias: {alias}" for alias in aliases))
        return Classification("unknown", "low", (f"ambiguous exact metric aliases: {', '.join(metrics)}",))
    if contained:
        longest = max(item[0] for item in contained)
        best = [(metric, alias) for length, metric, alias in contained if length == longest]
        metrics = sorted({metric for metric, _ in best})
        if len(metrics) == 1:
            return Classification(metrics[0], "medium", (f"metric phrase matched: {best[0][1]}",))
        return Classification("unknown", "low", (f"ambiguous metric phrases: {', '.join(metrics)}",))
    return Classification("unknown", "low", ("no deterministic metric alias matched",))


def detect_metrics(labels: list[str]) -> tuple[str, ...]:
    metrics: list[str] = []
    for label in labels:
        classification = classify_metric_label(label)
        if classification.value != "unknown" and classification.value not in metrics:
            metrics.append(classification.value)
    return tuple(metrics)


def classify_sheet(sheet_name: str, labels: list[str]) -> Classification:
    normalised_name = normalise_label(sheet_name)
    normalised_labels = [normalise_label(label) for label in labels]
    scored: list[tuple[int, str, tuple[str, ...]]] = []
    for role, rules in _ROLE_RULES.items():
        evidence: list[str] = []
        score = 0
        for term in rules["names"]:
            if normalise_label(term) in normalised_name:
                score += 5
                evidence.append(f"sheet name matched: {term}")
        for term in rules["metrics"]:
            normalized_term = normalise_label(term)
            if any(normalized_term in label for label in normalised_labels):
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
