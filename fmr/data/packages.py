from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

_CURRENCY = re.compile(r"^[A-Z]{3}$")


def _finite_decimal(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return False
    try:
        return Decimal(str(value)).is_finite()
    except InvalidOperation:
        return False


def validate_canonical_financial_data(payload: dict[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict) or payload.get("contract_version") != "canonical-financial-data.v2":
        return ("unsupported canonical financial data contract",)
    entity = payload.get("entity")
    if not isinstance(entity, dict) or not isinstance(entity.get("entity_id"), str) or not entity.get("entity_id"):
        issues.append("entity.entity_id is required")
    if not isinstance(entity, dict) or not isinstance(entity.get("currency"), str) or not _CURRENCY.fullmatch(entity.get("currency", "")):
        issues.append("entity.currency must be an ISO-style three-letter code")
    periods = payload.get("periods")
    if not isinstance(periods, list) or not periods or not all(isinstance(item, str) and item for item in periods) or len(set(periods)) != len(periods):
        issues.append("periods must be a unique non-empty array of strings")
    expected = len(periods) if isinstance(periods, list) else 0
    statements = payload.get("financial_statements")
    if not isinstance(statements, dict):
        issues.append("financial_statements must be an object")
    else:
        for statement_name, concepts in statements.items():
            if statement_name not in {"income_statement", "balance_sheet", "cash_flow"} or not isinstance(concepts, dict):
                issues.append(f"financial_statements.{statement_name} is invalid")
                continue
            for concept, values in concepts.items():
                if not isinstance(concept, str) or not isinstance(values, list) or len(values) != expected or not all(_finite_decimal(item) for item in values):
                    issues.append(f"financial_statements.{statement_name}.{concept} must contain one finite decimal per period")
    for section in ("trial_balance", "account_balances", "debt_schedules", "capital_expenditure", "working_capital"):
        if not isinstance(payload.get(section), list):
            issues.append(f"{section} must be an array")
    drivers = payload.get("operational_drivers")
    if not isinstance(drivers, dict):
        issues.append("operational_drivers must be an object")
    else:
        for name, values in drivers.items():
            if not isinstance(values, list) or len(values) != expected or not all(_finite_decimal(item) for item in values):
                issues.append(f"operational_drivers.{name} must contain one finite decimal per period")
    if not isinstance(payload.get("assumptions"), dict):
        issues.append("assumptions must be an object")
    provenance = payload.get("provenance")
    if not isinstance(provenance, list) or not provenance or not all(isinstance(item, dict) and isinstance(item.get("source"), str) and item["source"] for item in provenance):
        issues.append("provenance must contain source records")
    return tuple(dict.fromkeys(issues))


validate_canonical_model_input = validate_canonical_financial_data
