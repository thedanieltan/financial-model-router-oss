from __future__ import annotations

from collections import defaultdict
from typing import Any

from fmr.data import validate_canonical_financial_data
from fmr.financial_data import validate_financial_data_package, validate_mapping_result
from fmr.financial_data.common import CONCEPTS


def statement_mapping_to_canonical_data(package: dict[str, Any], mapping: dict[str, Any], *, assumptions: dict[str, Any] | None = None, operational_drivers: dict[str, list[Any]] | None = None) -> dict[str, Any]:
    issues = validate_financial_data_package(package)
    if issues:
        raise ValueError("invalid financial data package: " + "; ".join(issues))
    issues = validate_mapping_result(mapping, package=package)
    if issues:
        raise ValueError("invalid financial data mapping: " + "; ".join(issues))
    if mapping["blockers"]:
        raise ValueError("mapping blockers must be resolved before canonical conversion")
    periods = [item["period_id"] for item in package["periods"]]
    index = {period: position for position, period in enumerate(periods)}
    statements: dict[str, dict[str, list[str | None]]] = defaultdict(dict)
    for item in mapping["concept_series"]:
        concept = item["concept_id"]
        statement = CONCEPTS[concept]["statement_type"]
        if statement not in {"income_statement", "balance_sheet", "cash_flow"}:
            continue
        series = statements[statement].setdefault(concept, [None] * len(periods))
        series[index[item["period_id"]]] = item["amount"]
    incomplete = [
        f"{statement}.{concept}"
        for statement, concepts in statements.items()
        for concept, values in concepts.items()
        if any(value is None for value in values)
    ]
    if incomplete:
        raise ValueError("canonical conversion requires complete concept series: " + ", ".join(sorted(incomplete)))
    payload = {
        "contract_version": "canonical-financial-data.v2",
        "entity": package["entity"],
        "periods": periods,
        "financial_statements": dict(statements),
        "trial_balance": [],
        "account_balances": [],
        "debt_schedules": [],
        "capital_expenditure": [],
        "working_capital": [],
        "operational_drivers": dict(operational_drivers or {}),
        "assumptions": dict(assumptions or {}),
        "provenance": [{"source": package["source"]["filename"], "sha256": package["source"]["sha256"], "package_id": package["package_id"], "mapping_id": mapping["mapping_id"]}],
    }
    issues = validate_canonical_financial_data(payload)
    if issues:
        raise ValueError("canonical financial data is invalid: " + "; ".join(issues))
    return payload
