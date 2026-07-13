from __future__ import annotations

import hashlib
import json
import math
import re
from decimal import Decimal
from typing import Any

PACKAGE_ID_RE = re.compile(r"^fmrd_[0-9a-f]{24}$")
PROFILE_ID_RE = re.compile(r"^fmrmp_[0-9a-f]{24}$")
MAPPING_ID_RE = re.compile(r"^fmrm_[0-9a-f]{24}$")
BINDING_PROFILE_ID_RE = re.compile(r"^fmrbp_[0-9a-f]{24}$")
BINDING_PLAN_ID_RE = re.compile(r"^fmrbd_[0-9a-f]{24}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
ALLOWED_PERIOD_TYPES = {"actual", "budget", "forecast"}
ALLOWED_STATEMENTS = {
    "income_statement",
    "balance_sheet",
    "cash_flow",
    "operating_metric",
}
ALLOWED_BALANCE_TYPES = {"flow", "point_in_time"}
ALLOWED_SELECTORS = {"period_series", "latest", "repeat_latest"}

PACKAGE_CONTROLS = (
    "amounts_stored_as_decimal_strings",
    "duplicate_account_periods_rejected",
    "finite_amounts_only",
    "period_and_entity_consistency",
    "source_provenance_preserved",
)
MAPPING_CONTROLS = (
    "ambiguous_rows_block_binding",
    "exact_aliases_only",
    "explicit_profile_overrides",
    "source_rows_preserved",
    "unmapped_rows_reported",
)
BINDING_CONTROLS = (
    "binding_profile_uses_slot_ids",
    "complete_reserved_input_coverage_required",
    "input_set_emitted_only_when_ready",
    "no_record_id_mapping_required",
    "numeric_and_boolean_values_only",
    "source_contracts_pinned",
)

CONCEPTS: dict[str, dict[str, Any]] = {
    "revenue": {
        "statement_type": "income_statement",
        "balance_type": "flow",
        "aliases": ("revenue", "sales", "turnover", "net sales", "operating revenue"),
    },
    "operating_costs": {
        "statement_type": "income_statement",
        "balance_type": "flow",
        "aliases": ("operating costs", "operating expenses", "opex", "cost of sales"),
    },
    "cash": {
        "statement_type": "balance_sheet",
        "balance_type": "point_in_time",
        "aliases": ("cash", "cash and cash equivalents", "bank balances"),
    },
    "debt": {
        "statement_type": "balance_sheet",
        "balance_type": "point_in_time",
        "aliases": ("debt", "borrowings", "loans", "interest bearing debt"),
    },
    "accounts_receivable": {
        "statement_type": "balance_sheet",
        "balance_type": "point_in_time",
        "aliases": ("accounts receivable", "trade receivables", "receivables"),
    },
    "inventory": {
        "statement_type": "balance_sheet",
        "balance_type": "point_in_time",
        "aliases": ("inventory", "inventories", "stock"),
    },
    "accounts_payable": {
        "statement_type": "balance_sheet",
        "balance_type": "point_in_time",
        "aliases": ("accounts payable", "trade payables", "payables"),
    },
    "capital_expenditure": {
        "statement_type": "cash_flow",
        "balance_type": "flow",
        "aliases": (
            "capital expenditure",
            "capital expenditures",
            "capex",
            "purchase of property plant and equipment",
        ),
    },
    "depreciation": {
        "statement_type": "income_statement",
        "balance_type": "flow",
        "aliases": (
            "depreciation",
            "depreciation expense",
            "depreciation and amortisation",
            "depreciation and amortization",
        ),
    },
    "interest_expense": {
        "statement_type": "income_statement",
        "balance_type": "flow",
        "aliases": ("interest expense", "finance costs", "finance cost"),
    },
    "tax_expense": {
        "statement_type": "income_statement",
        "balance_type": "flow",
        "aliases": ("tax expense", "income tax expense", "corporate tax expense"),
    },
    "ebitda": {
        "statement_type": "income_statement",
        "balance_type": "flow",
        "aliases": (
            "ebitda",
            "earnings before interest tax depreciation and amortisation",
            "earnings before interest tax depreciation and amortization",
        ),
    },
    "operating_profit": {
        "statement_type": "income_statement",
        "balance_type": "flow",
        "aliases": ("operating profit", "operating income", "ebit"),
    },
    "net_income": {
        "statement_type": "income_statement",
        "balance_type": "flow",
        "aliases": ("net income", "net profit", "profit after tax"),
    },
    "operating_cash_flow": {
        "statement_type": "cash_flow",
        "balance_type": "flow",
        "aliases": (
            "operating cash flow",
            "cash flow from operations",
            "net cash from operating activities",
        ),
    },
}


def normalize_label(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


ALIAS_INDEX: dict[str, tuple[str, ...]] = {}
for concept_id, definition in CONCEPTS.items():
    for alias in definition["aliases"]:
        key = normalize_label(alias)
        ALIAS_INDEX[key] = tuple(
            sorted(set((*ALIAS_INDEX.get(key, ()), concept_id)))
        )


def digest(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


def decimal_string(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def json_number(value: Decimal) -> int | float:
    if value == value.to_integral():
        return int(value)
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(
            "financial value cannot be represented as a finite JSON number"
        )
    return number


def valid_value(value: Any, value_type: Any) -> bool:
    if value_type == "boolean":
        return isinstance(value, bool)
    if value_type == "number":
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
        )
    return False


def is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def concept_registry_payload() -> dict[str, Any]:
    items = [
        {
            "concept_id": concept_id,
            "statement_type": definition["statement_type"],
            "balance_type": definition["balance_type"],
            "aliases": list(definition["aliases"]),
        }
        for concept_id, definition in sorted(CONCEPTS.items())
    ]
    provisional = {
        "contract_version": "financial-concept-registry.v1",
        "concepts": items,
    }
    return {**provisional, "registry_sha256": digest(provisional)}


__all__ = [
    "ALIAS_INDEX",
    "ALLOWED_BALANCE_TYPES",
    "ALLOWED_PERIOD_TYPES",
    "ALLOWED_SELECTORS",
    "ALLOWED_STATEMENTS",
    "BINDING_CONTROLS",
    "BINDING_PLAN_ID_RE",
    "BINDING_PROFILE_ID_RE",
    "CONCEPTS",
    "CURRENCY_RE",
    "MAPPING_CONTROLS",
    "MAPPING_ID_RE",
    "PACKAGE_CONTROLS",
    "PACKAGE_ID_RE",
    "PROFILE_ID_RE",
    "concept_registry_payload",
    "decimal_string",
    "digest",
    "is_sha256",
    "json_number",
    "normalize_label",
    "valid_value",
]
