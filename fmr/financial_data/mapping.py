from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from fmr.financial_data.common import (
    ALIAS_INDEX,
    CONCEPTS,
    MAPPING_CONTROLS,
    MAPPING_ID_RE,
    PROFILE_ID_RE,
    decimal_string,
    digest,
    normalize_label,
)
from fmr.financial_data.package import validate_financial_data_package


def build_mapping_profile(
    rules: list[dict[str, Any]],
    *,
    name: str = "mapping profile",
) -> dict[str, Any]:
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
            raise ValueError(
                f"mapping rule {index} needs account_code or account_name"
            )
        normalized_rules.append(
            {
                "account_code": account_code,
                "account_name": account_name,
                "concept_id": rule["concept_id"],
            }
        )
    normalized_rules.sort(
        key=lambda item: (
            item["account_code"] or "",
            normalize_label(item["account_name"] or ""),
            item["concept_id"],
        )
    )
    provisional = {
        "contract_version": "financial-data-mapping-profile.v1",
        "name": name,
        "rules": normalized_rules,
    }
    payload = {
        **provisional,
        "profile_id": f"fmrmp_{digest(provisional)[:24]}",
    }
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
    if not isinstance(profile_id, str) or not PROFILE_ID_RE.fullmatch(profile_id):
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
            if not isinstance(rule, dict) or set(rule) != {
                "account_code",
                "account_name",
                "concept_id",
            }:
                issues.append(f"rules[{index}] fields are invalid")
                continue
            concept_id = rule.get("concept_id")
            if concept_id not in CONCEPTS:
                issues.append(f"rules[{index}].concept_id is unknown")
            if rule.get("account_code") is None and rule.get("account_name") is None:
                issues.append(
                    f"rules[{index}] needs account_code or account_name"
                )
            if isinstance(rule.get("account_code"), str):
                previous = seen_code.setdefault(rule["account_code"], concept_id)
                if previous != concept_id:
                    issues.append(
                        f"account_code {rule['account_code']} maps to multiple concepts"
                    )
            if isinstance(rule.get("account_name"), str):
                key = normalize_label(rule["account_name"])
                previous = seen_name.setdefault(key, concept_id)
                if previous != concept_id:
                    issues.append(
                        f"account_name {rule['account_name']} maps to multiple concepts"
                    )
    if isinstance(profile_id, str) and PROFILE_ID_RE.fullmatch(profile_id):
        candidate = dict(payload)
        candidate.pop("profile_id", None)
        if profile_id != f"fmrmp_{digest(candidate)[:24]}":
            issues.append("profile_id does not match payload")
    return tuple(dict.fromkeys(issues))


def map_financial_data(
    package: dict[str, Any],
    *,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    package_issues = validate_financial_data_package(package)
    if package_issues:
        raise ValueError(
            "financial data package is invalid: " + "; ".join(package_issues)
        )
    if profile is None:
        profile = build_mapping_profile([], name="built-in exact aliases")
    profile_issues = validate_mapping_profile(profile)
    if profile_issues:
        raise ValueError(
            "mapping profile is invalid: " + "; ".join(profile_issues)
        )

    by_code = {
        rule["account_code"]: rule["concept_id"]
        for rule in profile["rules"]
        if rule["account_code"] is not None
    }
    by_name = {
        normalize_label(rule["account_name"]): rule["concept_id"]
        for rule in profile["rules"]
        if rule["account_name"] is not None
    }
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
        normalized_name = normalize_label(row["account_name"])
        if normalized_name in by_name:
            candidates.add(by_name[normalized_name])
            methods.append("profile_account_name")
        if not candidates:
            alias_candidates = ALIAS_INDEX.get(normalized_name, ())
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
            if (
                row["statement_type"] != definition["statement_type"]
                or row["balance_type"] != definition["balance_type"]
            ):
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
        row_results.append(
            {
                "row_id": row["row_id"],
                "status": status,
                "concept_id": concept_id,
                "candidates": sorted(candidates),
                "method": (
                    methods[0]
                    if len(methods) == 1
                    else "combined_exact_rules"
                    if methods
                    else None
                ),
                "evidence": evidence,
            }
        )

    period_order = {
        period["period_id"]: index
        for index, period in enumerate(package["periods"])
    }
    series: list[dict[str, Any]] = []
    for (concept_id, period_id), amount in sorted(
        concept_periods.items(),
        key=lambda item: (item[0][0], period_order[item[0][1]]),
    ):
        series.append(
            {
                "concept_id": concept_id,
                "period_id": period_id,
                "amount": decimal_string(amount),
                "source_row_ids": sorted(
                    concept_sources[(concept_id, period_id)]
                ),
            }
        )

    provisional = {
        "contract_version": "financial-data-mapping-result.v1",
        "package_id": package["package_id"],
        "package_sha256": digest(package),
        "profile_id": profile["profile_id"],
        "profile_sha256": digest(profile),
        "row_mappings": row_results,
        "concept_series": series,
        "ready_for_binding": not blockers,
        "blockers": list(dict.fromkeys(blockers)),
        "controls": list(MAPPING_CONTROLS),
    }
    return {
        **provisional,
        "mapping_id": f"fmrm_{digest(provisional)[:24]}",
    }


def validate_mapping_result(
    payload: Any,
    *,
    package: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("mapping result must be an object",)
    expected = {
        "contract_version",
        "mapping_id",
        "package_id",
        "package_sha256",
        "profile_id",
        "profile_sha256",
        "row_mappings",
        "concept_series",
        "ready_for_binding",
        "blockers",
        "controls",
    }
    if set(payload) != expected:
        issues.append("mapping result fields are invalid")
    if payload.get("contract_version") != "financial-data-mapping-result.v1":
        issues.append("unsupported mapping result contract_version")
    mapping_id = payload.get("mapping_id")
    if not isinstance(mapping_id, str) or not MAPPING_ID_RE.fullmatch(mapping_id):
        issues.append("mapping_id is invalid")
    if payload.get("controls") != list(MAPPING_CONTROLS):
        issues.append("mapping controls are invalid")
    blockers = payload.get("blockers")
    if not isinstance(blockers, list) or not all(
        isinstance(item, str) and item for item in blockers
    ):
        issues.append("blockers must be an array of strings")
    if payload.get("ready_for_binding") is not (not bool(blockers)):
        issues.append("ready_for_binding does not match blockers")
    if package is not None:
        if payload.get("package_id") != package.get("package_id"):
            issues.append("package_id does not match package")
        if payload.get("package_sha256") != digest(package):
            issues.append("package_sha256 does not match package")
    if profile is not None:
        if payload.get("profile_id") != profile.get("profile_id"):
            issues.append("profile_id does not match profile")
        if payload.get("profile_sha256") != digest(profile):
            issues.append("profile_sha256 does not match profile")
    if isinstance(mapping_id, str) and MAPPING_ID_RE.fullmatch(mapping_id):
        candidate = dict(payload)
        candidate.pop("mapping_id", None)
        if mapping_id != f"fmrm_{digest(candidate)[:24]}":
            issues.append("mapping_id does not match payload")
    return tuple(dict.fromkeys(issues))


__all__ = [
    "build_mapping_profile",
    "map_financial_data",
    "validate_mapping_profile",
    "validate_mapping_result",
]
