from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from fmr.workbook.input_population import validate_workbook_input_set_payload
from fmr.workbook.write_plan_public import validate_workbook_write_plan_payload
from fmr.workbook.executor_public import validate_workbook_execution_receipt_payload

_PACKAGE_ID_RE = re.compile(r"^fmrd_[0-9a-f]{24}$")
_PROFILE_ID_RE = re.compile(r"^fmrmp_[0-9a-f]{24}$")
_MAPPING_ID_RE = re.compile(r"^fmrm_[0-9a-f]{24}$")
_BINDING_PROFILE_ID_RE = re.compile(r"^fmrbp_[0-9a-f]{24}$")
_BINDING_PLAN_ID_RE = re.compile(r"^fmrbd_[0-9a-f]{24}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_ALLOWED_PERIOD_TYPES = {"actual", "budget", "forecast"}
_ALLOWED_STATEMENTS = {
    "income_statement",
    "balance_sheet",
    "cash_flow",
    "operating_metric",
}
_ALLOWED_BALANCE_TYPES = {"flow", "point_in_time"}
_ALLOWED_SELECTORS = {"period_series", "latest", "repeat_latest"}
_PACKAGE_CONTROLS = (
    "amounts_stored_as_decimal_strings",
    "duplicate_account_periods_rejected",
    "finite_amounts_only",
    "period_and_entity_consistency",
    "source_provenance_preserved",
)
_MAPPING_CONTROLS = (
    "ambiguous_rows_block_binding",
    "exact_aliases_only",
    "explicit_profile_overrides",
    "source_rows_preserved",
    "unmapped_rows_reported",
)
_BINDING_CONTROLS = (
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
        "aliases": ("capital expenditure", "capital expenditures", "capex", "purchase of property plant and equipment"),
    },
    "depreciation": {
        "statement_type": "income_statement",
        "balance_type": "flow",
        "aliases": ("depreciation", "depreciation expense", "depreciation and amortisation", "depreciation and amortization"),
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
        "aliases": ("ebitda", "earnings before interest tax depreciation and amortisation", "earnings before interest tax depreciation and amortization"),
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
        "aliases": ("operating cash flow", "cash flow from operations", "net cash from operating activities"),
    },
}

_ALIAS_INDEX: dict[str, tuple[str, ...]] = {}
for concept_id, definition in CONCEPTS.items():
    for alias in definition["aliases"]:
        key = _normalize_label(alias)
        _ALIAS_INDEX[key] = tuple(sorted(set((*_ALIAS_INDEX.get(key, ()), concept_id))))


def import_statement_csv(csv_bytes: bytes, *, source_name: str) -> dict[str, Any]:
    if not isinstance(csv_bytes, bytes) or not csv_bytes:
        raise ValueError("statement CSV bytes must be non-empty")
    if not isinstance(source_name, str) or not source_name:
        raise ValueError("source_name must be non-empty")
    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("statement CSV must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text))
    expected = {
        "entity_id",
        "entity_name",
        "currency",
        "period_end",
        "period_type",
        "statement_type",
        "balance_type",
        "account_code",
        "account_name",
        "amount",
        "source_ref",
    }
    if reader.fieldnames is None or set(reader.fieldnames) != expected:
        raise ValueError("statement CSV columns do not match the required contract")

    entity: tuple[str, str, str] | None = None
    period_meta: dict[str, dict[str, str]] = {}
    grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    duplicate_keys: set[tuple[str, str, str, str, str, str]] = set()
    for line_number, raw in enumerate(reader, start=2):
        values = {key: (raw.get(key) or "").strip() for key in expected}
        if not all(values[key] for key in expected - {"account_code"}):
            raise ValueError(f"statement CSV row {line_number} contains blank required fields")
        current_entity = (
            values["entity_id"],
            values["entity_name"],
            values["currency"].upper(),
        )
        if entity is None:
            entity = current_entity
        elif current_entity != entity:
            raise ValueError("statement CSV must contain exactly one entity and currency")
        if not _CURRENCY_RE.fullmatch(current_entity[2]):
            raise ValueError(f"statement CSV row {line_number} currency must be ISO-style uppercase")
        try:
            date.fromisoformat(values["period_end"])
        except ValueError as exc:
            raise ValueError(f"statement CSV row {line_number} period_end must be YYYY-MM-DD") from exc
        if values["period_type"] not in _ALLOWED_PERIOD_TYPES:
            raise ValueError(f"statement CSV row {line_number} period_type is invalid")
        if values["statement_type"] not in _ALLOWED_STATEMENTS:
            raise ValueError(f"statement CSV row {line_number} statement_type is invalid")
        if values["balance_type"] not in _ALLOWED_BALANCE_TYPES:
            raise ValueError(f"statement CSV row {line_number} balance_type is invalid")
        if values["statement_type"] in {"income_statement", "cash_flow"} and values["balance_type"] != "flow":
            raise ValueError(f"statement CSV row {line_number} must use flow balance_type")
        if values["statement_type"] == "balance_sheet" and values["balance_type"] != "point_in_time":
            raise ValueError(f"statement CSV row {line_number} must use point_in_time balance_type")
        amount = _parse_decimal(values["amount"], line_number)
        period_id = f"{values['period_end']}:{values['period_type']}"
        period_meta[period_id] = {
            "period_id": period_id,
            "period_end": values["period_end"],
            "period_type": values["period_type"],
        }
        row_key = (
            values["statement_type"],
            values["balance_type"],
            values["account_code"],
            values["account_name"],
            values["source_ref"],
        )
        duplicate_key = (*row_key, period_id)
        if duplicate_key in duplicate_keys:
            raise ValueError(f"statement CSV row {line_number} duplicates an account-period value")
        duplicate_keys.add(duplicate_key)
        item = grouped.setdefault(
            row_key,
            {
                "statement_type": values["statement_type"],
                "balance_type": values["balance_type"],
                "account_code": values["account_code"] or None,
                "account_name": values["account_name"],
                "source_ref": values["source_ref"],
                "values": [],
            },
        )
        item["values"].append({"period_id": period_id, "amount": _decimal_string(amount)})
    if entity is None or not grouped:
        raise ValueError("statement CSV contains no data rows")

    periods = sorted(period_meta.values(), key=lambda item: (item["period_end"], item["period_type"]))
    period_order = {item["period_id"]: index for index, item in enumerate(periods)}
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(
        sorted(grouped.values(), key=lambda row: (row["statement_type"], row["account_code"] or "", row["account_name"], row["source_ref"])),
        start=1,
    ):
        item["values"].sort(key=lambda value: period_order[value["period_id"]])
        rows.append({"row_id": f"row_{index:06d}", **item})

    provisional = {
        "contract_version": "financial-data-package.v1",
        "source": {
            "kind": "statement_csv",
            "filename": source_name,
            "sha256": hashlib.sha256(csv_bytes).hexdigest(),
            "size_bytes": len(csv_bytes),
        },
        "entity": {"entity_id": entity[0], "entity_name": entity[1], "currency": entity[2]},
        "periods": periods,
        "rows": rows,
        "controls": list(_PACKAGE_CONTROLS),
    }
    payload = {**provisional, "package_id": f"fmrd_{_digest(provisional)[:24]}"}
    issues = validate_financial_data_package(payload)
    if issues:
        raise ValueError("compiled financial data package is invalid: " + "; ".join(issues))
    return payload


def validate_financial_data_package(payload: Any) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("financial data package must be an object",)
    expected = {"contract_version", "package_id", "source", "entity", "periods", "rows", "controls"}
    if set(payload) != expected:
        issues.append("financial data package fields are invalid")
    if payload.get("contract_version") != "financial-data-package.v1":
        issues.append("unsupported contract_version")
    package_id = payload.get("package_id")
    if not isinstance(package_id, str) or not _PACKAGE_ID_RE.fullmatch(package_id):
        issues.append("package_id is invalid")
    source = payload.get("source")
    if not isinstance(source, dict) or set(source) != {"kind", "filename", "sha256", "size_bytes"}:
        issues.append("source fields are invalid")
    elif source.get("kind") != "statement_csv" or not _is_sha256(source.get("sha256")) or not isinstance(source.get("size_bytes"), int) or source.get("size_bytes") <= 0:
        issues.append("source metadata is invalid")
    entity = payload.get("entity")
    if not isinstance(entity, dict) or set(entity) != {"entity_id", "entity_name", "currency"}:
        issues.append("entity fields are invalid")
    elif not all(isinstance(entity.get(key), str) and entity.get(key) for key in ("entity_id", "entity_name")) or not _CURRENCY_RE.fullmatch(entity.get("currency", "")):
        issues.append("entity values are invalid")
    periods = payload.get("periods")
    period_ids: list[str] = []
    if not isinstance(periods, list) or not periods:
        issues.append("periods must be a non-empty array")
    else:
        for index, period in enumerate(periods):
            if not isinstance(period, dict) or set(period) != {"period_id", "period_end", "period_type"}:
                issues.append(f"periods[{index}] fields are invalid")
                continue
            period_ids.append(period.get("period_id"))
            try:
                date.fromisoformat(period.get("period_end", ""))
            except (TypeError, ValueError):
                issues.append(f"periods[{index}].period_end is invalid")
            if period.get("period_type") not in _ALLOWED_PERIOD_TYPES:
                issues.append(f"periods[{index}].period_type is invalid")
            if period.get("period_id") != f"{period.get('period_end')}:{period.get('period_type')}":
                issues.append(f"periods[{index}].period_id is invalid")
        if len(period_ids) != len(set(period_ids)):
            issues.append("period IDs must be unique")
    rows = payload.get("rows")
    row_ids: list[str] = []
    if not isinstance(rows, list) or not rows:
        issues.append("rows must be a non-empty array")
    else:
        allowed_periods = set(period_ids)
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or set(row) != {"row_id", "statement_type", "balance_type", "account_code", "account_name", "source_ref", "values"}:
                issues.append(f"rows[{index}] fields are invalid")
                continue
            row_ids.append(row.get("row_id"))
            if row.get("statement_type") not in _ALLOWED_STATEMENTS or row.get("balance_type") not in _ALLOWED_BALANCE_TYPES:
                issues.append(f"rows[{index}] statement or balance type is invalid")
            if not isinstance(row.get("account_name"), str) or not row.get("account_name") or not isinstance(row.get("source_ref"), str) or not row.get("source_ref"):
                issues.append(f"rows[{index}] account_name and source_ref must be non-empty")
            values = row.get("values")
            seen: set[str] = set()
            if not isinstance(values, list) or not values:
                issues.append(f"rows[{index}].values must be non-empty")
            else:
                for value_index, value in enumerate(values):
                    if not isinstance(value, dict) or set(value) != {"period_id", "amount"}:
                        issues.append(f"rows[{index}].values[{value_index}] fields are invalid")
                        continue
                    if value.get("period_id") not in allowed_periods:
                        issues.append(f"rows[{index}].values[{value_index}].period_id is unknown")
                    if value.get("period_id") in seen:
                        issues.append(f"rows[{index}] repeats a period")
                    seen.add(value.get("period_id"))
                    try:
                        amount = Decimal(value.get("amount", ""))
                        if not amount.is_finite():
                            raise InvalidOperation
                    except (InvalidOperation, TypeError):
                        issues.append(f"rows[{index}].values[{value_index}].amount is invalid")
        if len(row_ids) != len(set(row_ids)):
            issues.append("row IDs must be unique")
    if payload.get("controls") != list(_PACKAGE_CONTROLS):
        issues.append("controls do not match the required package controls")
    if isinstance(package_id, str) and _PACKAGE_ID_RE.fullmatch(package_id):
        candidate = dict(payload)
        candidate.pop("package_id", None)
        if package_id != f"fmrd_{_digest(candidate)[:24]}":
            issues.append("package_id does not match payload")
    return tuple(dict.fromkeys(issues))


def build_mapping_profile(rules: list[dict[str, Any]], *, name: str = "mapping profile") -> dict[str, Any]:
    normalized_rules: list[dict[str, Any]] = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"mapping rule {index} must be an object")
        expected = {"account_code", "account_name", "concept_id"}
        if set(rule) != expected:
            raise ValueError(f"mapping rule {index} fields are invalid")
        if rule["concept_id"] not in CONCEPTS:
            raise ValueError(f"mapping rule {index} concept_id is unknown")
        account_code = rule["account_code"] or None
        account_name = rule["account_name"] or None
        if account_code is None and account_name is None:
            raise ValueError(f"mapping rule {index} needs account_code or account_name")
        normalized_rules.append({"account_code": account_code, "account_name": account_name, "concept_id": rule["concept_id"]})
    normalized_rules.sort(key=lambda item: (item["account_code"] or "", _normalize_label(item["account_name"] or ""), item["concept_id"]))
    provisional = {"contract_version": "financial-data-mapping-profile.v1", "name": name, "rules": normalized_rules}
    payload = {**provisional, "profile_id": f"fmrmp_{_digest(provisional)[:24]}"}
    issues = validate_mapping_profile(payload)
    if issues:
        raise ValueError("mapping profile is invalid: " + "; ".join(issues))
    return payload


def validate_mapping_profile(payload: Any) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("mapping profile must be an object",)
    if set(payload) != {"contract_version", "profile_id", "name", "rules"}:
        issues.append("mapping profile fields are invalid")
    if payload.get("contract_version") != "financial-data-mapping-profile.v1":
        issues.append("unsupported mapping profile contract_version")
    profile_id = payload.get("profile_id")
    if not isinstance(profile_id, str) or not _PROFILE_ID_RE.fullmatch(profile_id):
        issues.append("profile_id is invalid")
    if not isinstance(payload.get("name"), str) or not payload.get("name"):
        issues.append("mapping profile name must be non-empty")
    rules = payload.get("rules")
    seen_code: dict[str, str] = {}
    seen_name: dict[str, str] = {}
    if not isinstance(rules, list):
        issues.append("mapping profile rules must be an array")
    else:
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict) or set(rule) != {"account_code", "account_name", "concept_id"}:
                issues.append(f"rules[{index}] fields are invalid")
                continue
            if rule.get("concept_id") not in CONCEPTS:
                issues.append(f"rules[{index}].concept_id is unknown")
            if rule.get("account_code") is None and rule.get("account_name") is None:
                issues.append(f"rules[{index}] needs account_code or account_name")
            if isinstance(rule.get("account_code"), str):
                previous = seen_code.setdefault(rule["account_code"], rule.get("concept_id"))
                if previous != rule.get("concept_id"):
                    issues.append(f"account_code {rule['account_code']} maps to multiple concepts")
            if isinstance(rule.get("account_name"), str):
                key = _normalize_label(rule["account_name"])
                previous = seen_name.setdefault(key, rule.get("concept_id"))
                if previous != rule.get("concept_id"):
                    issues.append(f"account_name {rule['account_name']} maps to multiple concepts")
    if isinstance(profile_id, str) and _PROFILE_ID_RE.fullmatch(profile_id):
        candidate = dict(payload)
        candidate.pop("profile_id", None)
        if profile_id != f"fmrmp_{_digest(candidate)[:24]}":
            issues.append("profile_id does not match payload")
    return tuple(dict.fromkeys(issues))


def map_financial_data(package: dict[str, Any], *, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    package_issues = validate_financial_data_package(package)
    if package_issues:
        raise ValueError("financial data package is invalid: " + "; ".join(package_issues))
    if profile is None:
        profile = build_mapping_profile([], name="built-in exact aliases")
    profile_issues = validate_mapping_profile(profile)
    if profile_issues:
        raise ValueError("mapping profile is invalid: " + "; ".join(profile_issues))
    by_code = {rule["account_code"]: rule["concept_id"] for rule in profile["rules"] if rule["account_code"] is not None}
    by_name = {_normalize_label(rule["account_name"]): rule["concept_id"] for rule in profile["rules"] if rule["account_name"] is not None}
    row_results: list[dict[str, Any]] = []
    concept_periods: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    concept_sources: dict[tuple[str, str], list[str]] = defaultdict(list)
    blockers: list[str] = []
    for row in package["rows"]:
        candidates: set[str] = set()
        methods: list[str] = []
        if row["account_code"] in by_code:
            candidates.add(by_code[row["account_code"]])
            methods.append("profile_account_code")
        normalized_name = _normalize_label(row["account_name"])
        if normalized_name in by_name:
            candidates.add(by_name[normalized_name])
            methods.append("profile_account_name")
        if not candidates:
            alias_candidates = _ALIAS_INDEX.get(normalized_name, ())
            candidates.update(alias_candidates)
            if alias_candidates:
                methods.append("built_in_exact_alias")
        status = "unmapped"
        concept_id: str | None = None
        evidence: list[str] = []
        if len(candidates) > 1:
            status = "ambiguous"
            blockers.append(f"{row['row_id']}:ambiguous_mapping")
            evidence.append("multiple_exact_candidates")
        elif len(candidates) == 1:
            concept_id = next(iter(candidates))
            definition = CONCEPTS[concept_id]
            if row["statement_type"] != definition["statement_type"] or row["balance_type"] != definition["balance_type"]:
                status = "invalid"
                blockers.append(f"{row['row_id']}:concept_shape_mismatch")
                evidence.append("statement_or_balance_type_mismatch")
            else:
                status = "mapped"
                evidence.extend(methods)
                for value in row["values"]:
                    key = (concept_id, value["period_id"])
                    concept_periods[key] += Decimal(value["amount"])
                    concept_sources[key].append(row["row_id"])
        row_results.append({
            "row_id": row["row_id"],
            "status": status,
            "concept_id": concept_id,
            "candidates": sorted(candidates),
            "method": methods[0] if len(methods) == 1 else ("combined_exact_rules" if methods else None),
            "evidence": evidence,
        })
    series: list[dict[str, Any]] = []
    period_order = {period["period_id"]: index for index, period in enumerate(package["periods"])}
    for (concept_id, period_id), amount in sorted(concept_periods.items(), key=lambda item: (item[0][0], period_order[item[0][1]])):
        series.append({
            "concept_id": concept_id,
            "period_id": period_id,
            "amount": _decimal_string(amount),
            "source_row_ids": sorted(concept_sources[(concept_id, period_id)]),
        })
    provisional = {
        "contract_version": "financial-data-mapping-result.v1",
        "package_id": package["package_id"],
        "package_sha256": _digest(package),
        "profile_id": profile["profile_id"],
        "profile_sha256": _digest(profile),
        "row_mappings": row_results,
        "concept_series": series,
        "ready_for_binding": not blockers,
        "blockers": list(dict.fromkeys(blockers)),
        "controls": list(_MAPPING_CONTROLS),
    }
    return {**provisional, "mapping_id": f"fmrm_{_digest(provisional)[:24]}"}


def build_binding_profile(bindings: list[dict[str, Any]], *, name: str = "binding profile") -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            raise ValueError(f"binding {index} must be an object")
        source_type = binding.get("source_type")
        if source_type == "concept":
            expected = {"slot_id", "source_type", "concept_id", "selector"}
            if set(binding) != expected or binding.get("concept_id") not in CONCEPTS or binding.get("selector") not in _ALLOWED_SELECTORS:
                raise ValueError(f"binding {index} concept fields are invalid")
            normalized.append(dict(binding))
        elif source_type == "constant":
            expected = {"slot_id", "source_type", "value_type", "value"}
            if set(binding) != expected or binding.get("value_type") not in {"number", "boolean"} or not _valid_value(binding.get("value"), binding.get("value_type")):
                raise ValueError(f"binding {index} constant fields are invalid")
            normalized.append(dict(binding))
        else:
            raise ValueError(f"binding {index} source_type is invalid")
    normalized.sort(key=lambda item: item["slot_id"])
    provisional = {"contract_version": "financial-data-binding-profile.v1", "name": name, "bindings": normalized}
    return {**provisional, "binding_profile_id": f"fmrbp_{_digest(provisional)[:24]}"}


def plan_financial_input_bindings(
    package: dict[str, Any],
    mapping_result: dict[str, Any],
    binding_profile: dict[str, Any],
    *,
    write_plan: dict[str, Any],
    execution_receipt: dict[str, Any],
) -> dict[str, Any]:
    package_issues = validate_financial_data_package(package)
    if package_issues:
        raise ValueError("financial data package is invalid: " + "; ".join(package_issues))
    plan_issues = validate_workbook_write_plan_payload(write_plan)
    if plan_issues:
        raise ValueError("workbook write plan is invalid: " + "; ".join(plan_issues))
    receipt_issues = validate_workbook_execution_receipt_payload(execution_receipt, write_plan=write_plan)
    if receipt_issues:
        raise ValueError("execution receipt is invalid: " + "; ".join(receipt_issues))
    if mapping_result.get("contract_version") != "financial-data-mapping-result.v1" or mapping_result.get("package_id") != package["package_id"] or mapping_result.get("package_sha256") != _digest(package):
        raise ValueError("mapping result does not match the financial data package")
    if binding_profile.get("contract_version") != "financial-data-binding-profile.v1" or not _BINDING_PROFILE_ID_RE.fullmatch(binding_profile.get("binding_profile_id", "")):
        raise ValueError("binding profile is invalid")
    profile_by_slot = {item["slot_id"]: item for item in binding_profile.get("bindings", [])}
    if len(profile_by_slot) != len(binding_profile.get("bindings", [])):
        raise ValueError("binding profile contains duplicate slot IDs")
    period_order = [period["period_id"] for period in package["periods"]]
    concept_values: dict[str, dict[str, Decimal]] = defaultdict(dict)
    for item in mapping_result.get("concept_series", []):
        concept_values[item["concept_id"]][item["period_id"]] = Decimal(item["amount"])
    bound: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for record in _reserved_records(write_plan):
        slot_id = record.get("slot_id")
        profile_item = profile_by_slot.get(slot_id)
        cell_count = _coordinate_cell_count(record["coordinate"])
        if profile_item is None:
            unresolved.append({"record_id": record["record_id"], "slot_id": slot_id, "reason": "binding_profile_missing_slot"})
            continue
        if profile_item["source_type"] == "constant":
            values = [profile_item["value"]] * cell_count
            bound.append({
                "record_id": record["record_id"],
                "slot_id": slot_id,
                "value_type": profile_item["value_type"],
                "values": values,
                "source_ref": f"financial-binding-profile:{binding_profile['binding_profile_id']}:{slot_id}",
            })
            continue
        concept_id = profile_item["concept_id"]
        available = concept_values.get(concept_id, {})
        ordered = [available[period_id] for period_id in period_order if period_id in available]
        selector = profile_item["selector"]
        if not ordered:
            unresolved.append({"record_id": record["record_id"], "slot_id": slot_id, "reason": f"concept_has_no_values:{concept_id}"})
            continue
        selected: list[Decimal]
        if selector == "period_series":
            selected = ordered
        elif selector == "latest":
            selected = [ordered[-1]]
        else:
            selected = [ordered[-1]] * cell_count
        if len(selected) != cell_count:
            unresolved.append({"record_id": record["record_id"], "slot_id": slot_id, "reason": f"concept_value_count_mismatch:{concept_id}:{len(selected)}:{cell_count}"})
            continue
        bound.append({
            "record_id": record["record_id"],
            "slot_id": slot_id,
            "value_type": "number",
            "values": [_json_number(value) for value in selected],
            "source_ref": f"financial-data:{package['package_id']}:{concept_id}:{selector}",
        })
    blockers = [f"{item['record_id']}:{item['reason']}" for item in unresolved]
    if not mapping_result.get("ready_for_binding"):
        blockers.extend(f"mapping:{item}" for item in mapping_result.get("blockers", []))
    provisional = {
        "contract_version": "workbook-input-binding-plan.v1",
        "package_id": package["package_id"],
        "package_sha256": _digest(package),
        "mapping_id": mapping_result["mapping_id"],
        "mapping_sha256": _digest(mapping_result),
        "binding_profile_id": binding_profile["binding_profile_id"],
        "binding_profile_sha256": _digest(binding_profile),
        "write_plan_id": write_plan["write_plan_id"],
        "write_plan_sha256": _digest(write_plan),
        "execution_id": execution_receipt["execution_id"],
        "execution_receipt_sha256": _digest(execution_receipt),
        "bound_records": bound,
        "unresolved_records": unresolved,
        "ready_for_input_set": not blockers,
        "blockers": list(dict.fromkeys(blockers)),
        "controls": list(_BINDING_CONTROLS),
    }
    return {**provisional, "binding_plan_id": f"fmrbd_{_digest(provisional)[:24]}"}


def compile_input_set_from_binding_plan(
    binding_plan: dict[str, Any],
    *,
    write_plan: dict[str, Any],
    execution_receipt: dict[str, Any],
) -> dict[str, Any]:
    if binding_plan.get("contract_version") != "workbook-input-binding-plan.v1" or not _BINDING_PLAN_ID_RE.fullmatch(binding_plan.get("binding_plan_id", "")):
        raise ValueError("binding plan is invalid")
    if not binding_plan.get("ready_for_input_set") or binding_plan.get("blockers"):
        raise ValueError("binding plan is not ready for an input set")
    if binding_plan.get("write_plan_id") != write_plan.get("write_plan_id") or binding_plan.get("write_plan_sha256") != _digest(write_plan):
        raise ValueError("binding plan does not match the write plan")
    if binding_plan.get("execution_id") != execution_receipt.get("execution_id") or binding_plan.get("execution_receipt_sha256") != _digest(execution_receipt):
        raise ValueError("binding plan does not match the execution receipt")
    rendered = json.dumps(binding_plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    provisional = {
        "contract_version": "workbook-input-set.v1",
        "write_plan_id": write_plan["write_plan_id"],
        "write_plan_sha256": _digest(write_plan),
        "execution_id": execution_receipt["execution_id"],
        "execution_receipt_sha256": _digest(execution_receipt),
        "source": {
            "kind": "system",
            "reference": f"financial-data-binding-plan:{binding_plan['binding_plan_id']}",
            "sha256": hashlib.sha256(rendered).hexdigest(),
            "size_bytes": len(rendered),
        },
        "bindings": [
            {
                "record_id": item["record_id"],
                "value_type": item["value_type"],
                "values": item["values"],
                "source_ref": item["source_ref"],
            }
            for item in binding_plan["bound_records"]
        ],
        "controls": [
            "complete_reserved_input_coverage",
            "execution_receipt_pinned",
            "explicit_record_binding",
            "finite_values_only",
            "formulas_forbidden",
            "source_provenance_declared",
            "write_plan_pinned",
        ],
    }
    payload = {**provisional, "input_set_id": f"fmri_{_digest(provisional)[:24]}"}
    issues = validate_workbook_input_set_payload(payload, write_plan=write_plan, execution_receipt=execution_receipt)
    if issues:
        raise ValueError("compiled input set is invalid: " + "; ".join(issues))
    return payload


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
    provisional = {"contract_version": "financial-concept-registry.v1", "concepts": items}
    return {**provisional, "registry_sha256": _digest(provisional)}


def _reserved_records(write_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [record for phase in write_plan.get("phases", []) for record in phase.get("records", []) if isinstance(record, dict) and record.get("write_kind") == "reserve_input"]


def _coordinate_cell_count(coordinate: str) -> int:
    match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]*)(?::([A-Z]{1,3})([1-9][0-9]*))?", coordinate or "")
    if not match:
        raise ValueError("coordinate is invalid")
    start_col, start_row, end_col, end_row = match.groups()
    end_col = end_col or start_col
    end_row = end_row or start_row
    return (_column_number(end_col) - _column_number(start_col) + 1) * (int(end_row) - int(start_row) + 1)


def _column_number(label: str) -> int:
    value = 0
    for character in label:
        value = value * 26 + ord(character) - ord("A") + 1
    return value


def _normalize_label(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _parse_decimal(value: str, line_number: int) -> Decimal:
    try:
        amount = Decimal(value.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"statement CSV row {line_number} amount is invalid") from exc
    if not amount.is_finite():
        raise ValueError(f"statement CSV row {line_number} amount must be finite")
    return amount


def _decimal_string(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _json_number(value: Decimal) -> int | float:
    if value == value.to_integral():
        return int(value)
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("financial value cannot be represented as a finite JSON number")
    return number


def _valid_value(value: Any, value_type: Any) -> bool:
    if value_type == "boolean":
        return isinstance(value, bool)
    if value_type == "number":
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))
    return False


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _digest(payload: Any) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


__all__ = [
    "CONCEPTS",
    "build_binding_profile",
    "build_mapping_profile",
    "compile_input_set_from_binding_plan",
    "concept_registry_payload",
    "import_statement_csv",
    "map_financial_data",
    "plan_financial_input_bindings",
    "validate_financial_data_package",
    "validate_mapping_profile",
]
