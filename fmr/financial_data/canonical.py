from __future__ import annotations

import hashlib
import json
import tempfile
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fmr.data import validate_canonical_financial_data
from fmr.financial_data.common import CONCEPTS, digest
from fmr.financial_data.mapping import (
    build_mapping_profile,
    map_financial_data,
    validate_mapping_result,
)
from fmr.financial_data.package import (
    import_statement_csv,
    validate_financial_data_package,
)


def _finite_decimal(value: Any, field: str) -> str:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite decimal")
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite decimal") from exc
    if not decimal.is_finite():
        raise ValueError(f"{field} must be a finite decimal")
    normalized = decimal.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _validate_assumptions(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and key for key in value
    ):
        raise ValueError("assumptions must be an object with non-empty string keys")
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    loaded = json.loads(rendered)
    if not isinstance(loaded, dict):
        raise ValueError("assumptions must be a JSON object")
    return loaded


def _validate_driver_series(
    value: Any,
    *,
    periods: tuple[str, ...],
) -> dict[str, list[str]]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and key for key in value
    ):
        raise ValueError(
            "operational_drivers must be an object with non-empty string keys"
        )
    result: dict[str, list[str]] = {}
    for name, series in sorted(value.items()):
        if not isinstance(series, list) or len(series) != len(periods):
            raise ValueError(
                f"operational_drivers.{name} must contain one value per period"
            )
        result[name] = [
            _finite_decimal(item, f"operational_drivers.{name}") for item in series
        ]
    return result


def compile_canonical_financial_data(
    package: dict[str, Any],
    mapping_result: dict[str, Any],
    *,
    assumptions: dict[str, Any] | None = None,
    operational_drivers: dict[str, list[Any]] | None = None,
) -> dict[str, Any]:
    package_issues = validate_financial_data_package(package)
    if package_issues:
        raise ValueError(
            "financial data package is invalid: " + "; ".join(package_issues)
        )
    mapping_issues = validate_mapping_result(mapping_result, package=package)
    if mapping_issues:
        raise ValueError(
            "financial mapping result is invalid: " + "; ".join(mapping_issues)
        )
    if mapping_result["blockers"]:
        raise ValueError(
            "financial mapping is blocked: " + "; ".join(mapping_result["blockers"])
        )

    periods = tuple(period["period_id"] for period in package["periods"])
    period_index = {period: index for index, period in enumerate(periods)}
    concept_values: dict[str, list[str | None]] = {}
    for item in mapping_result["concept_series"]:
        concept = item["concept_id"]
        values = concept_values.setdefault(concept, [None] * len(periods))
        index = period_index.get(item["period_id"])
        if index is None:
            raise ValueError("mapped concept references an unknown period")
        if values[index] is not None:
            raise ValueError(
                f"mapped concept {concept} contains a duplicate period value"
            )
        values[index] = _finite_decimal(
            item["amount"], f"concept_series.{concept}.{item['period_id']}"
        )

    incomplete = sorted(
        concept
        for concept, values in concept_values.items()
        if any(value is None for value in values)
    )
    if incomplete:
        raise ValueError(
            "mapped concepts must cover every period: " + ",".join(incomplete)
        )

    statements: dict[str, dict[str, list[str]]] = {
        "income_statement": {},
        "balance_sheet": {},
        "cash_flow": {},
    }
    mapped_drivers: dict[str, list[str]] = {}
    for concept, values in sorted(concept_values.items()):
        definition = CONCEPTS[concept]
        completed = [str(value) for value in values]
        if definition["statement_type"] == "operating_metric":
            mapped_drivers[concept] = completed
        else:
            statements[definition["statement_type"]][concept] = completed

    explicit_drivers = _validate_driver_series(
        operational_drivers,
        periods=periods,
    )
    conflicts = sorted(set(mapped_drivers).intersection(explicit_drivers))
    if conflicts:
        raise ValueError(
            "operational drivers cannot override mapped concepts: "
            + ",".join(conflicts)
        )
    drivers = {**mapped_drivers, **explicit_drivers}

    trial_balance = [
        {
            "row_id": row["row_id"],
            "account_code": row["account_code"],
            "account_name": row["account_name"],
            "statement_type": row["statement_type"],
            "balance_type": row["balance_type"],
            "source_ref": row["source_ref"],
            "values": list(row["values"]),
        }
        for row in package["rows"]
    ]
    capital_expenditure = [
        {"period": period, "amount": amount}
        for period, amount in zip(
            periods,
            concept_values.get("capital_expenditure", []),
            strict=False,
        )
    ]
    working_capital_concepts = (
        "accounts_receivable",
        "inventory",
        "accounts_payable",
    )
    working_capital: list[dict[str, Any]] = []
    for concept in working_capital_concepts:
        for period, amount in zip(
            periods,
            concept_values.get(concept, []),
            strict=False,
        ):
            working_capital.append(
                {"period": period, "concept_id": concept, "amount": amount}
            )

    canonical = {
        "contract_version": "canonical-financial-data.v2",
        "entity": {
            "entity_id": package["entity"]["entity_id"],
            "entity_name": package["entity"]["entity_name"],
            "currency": package["entity"]["currency"],
        },
        "periods": list(periods),
        "financial_statements": {
            name: values for name, values in statements.items() if values
        },
        "trial_balance": trial_balance,
        "account_balances": [],
        "debt_schedules": [],
        "capital_expenditure": capital_expenditure,
        "working_capital": working_capital,
        "operational_drivers": drivers,
        "assumptions": _validate_assumptions(assumptions),
        "provenance": [
            {
                "source": "statement_csv",
                "sha256": package["source"]["sha256"],
                "package_id": package["package_id"],
                "mapping_id": mapping_result["mapping_id"],
            }
        ],
    }
    issues = validate_canonical_financial_data(canonical)
    if issues:
        raise ValueError(
            "compiled canonical financial data is invalid: " + "; ".join(issues)
        )
    return canonical


def derive_available_data(canonical: dict[str, Any]) -> tuple[str, ...]:
    issues = validate_canonical_financial_data(canonical)
    if issues:
        raise ValueError("canonical financial data is invalid: " + "; ".join(issues))
    available: set[str] = set()
    statements = canonical["financial_statements"]
    if statements.get("income_statement"):
        available.add("income_statement_history")
    if statements.get("balance_sheet"):
        available.add("balance_sheet_history")
    if statements.get("cash_flow"):
        available.add("cash_flow_history")
    if canonical["capital_expenditure"]:
        available.add("capital_expenditure")
    if canonical["working_capital"]:
        available.add("working_capital")
    balance_sheet = statements.get("balance_sheet", {})
    if "cash" in balance_sheet:
        available.add("liquidity_position")
    drivers = set(canonical["operational_drivers"])
    if drivers.intersection(
        {
            "revenue_units",
            "unit_price",
            "customer_count",
            "monthly_recurring_revenue",
        }
    ):
        available.add("revenue_drivers")
    if drivers.intersection({"headcount", "operating_costs", "salary_cost"}):
        available.add("operating_cost_drivers")
    if "customer_count" in drivers:
        available.add("customer_history")
    if "monthly_recurring_revenue" in drivers:
        available.add("monthly_recurring_revenue_history")
    return tuple(sorted(available))


class WorkflowSourceStore:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(
            root or Path(tempfile.gettempdir()) / "fmr-workflow-sources-v1"
        ).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def store(self, canonical: dict[str, Any]) -> dict[str, str]:
        issues = validate_canonical_financial_data(canonical)
        if issues:
            raise ValueError(
                "canonical financial data is invalid: " + "; ".join(issues)
            )
        payload = (
            json.dumps(canonical, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        sha256 = hashlib.sha256(payload).hexdigest()
        target = (self.root / f"{sha256}.json").resolve()
        if self.root not in target.parents:
            raise ValueError("workflow source path escaped the managed root")
        if target.exists():
            if target.read_bytes() != payload:
                raise RuntimeError("existing workflow source hash does not match")
        else:
            temporary = self.root / f".{sha256}.tmp"
            temporary.write_bytes(payload)
            temporary.replace(target)
        return {
            "contract_version": "canonical-financial-data.v2",
            "path": str(target),
            "sha256": sha256,
        }


def create_statement_csv_workflow_source(
    csv_bytes: bytes,
    *,
    source_name: str,
    mapping_rules: list[dict[str, Any]] | None = None,
    assumptions: dict[str, Any] | None = None,
    operational_drivers: dict[str, list[Any]] | None = None,
    store: WorkflowSourceStore | None = None,
) -> dict[str, Any]:
    package = import_statement_csv(csv_bytes, source_name=source_name)
    profile = build_mapping_profile(
        mapping_rules or [],
        name=f"workflow source mapping for {source_name}",
    )
    mapping = map_financial_data(package, profile=profile)
    canonical = compile_canonical_financial_data(
        package,
        mapping,
        assumptions=assumptions,
        operational_drivers=operational_drivers,
    )
    reference = (store or WorkflowSourceStore()).store(canonical)
    unmapped = sorted(
        item["row_id"]
        for item in mapping["row_mappings"]
        if item["status"] == "unmapped"
    )
    warnings = [f"unmapped_source_row:{row_id}" for row_id in unmapped]
    provisional = {
        "contract_version": "workflow-source-result.v1",
        "source_kind": "statement_csv",
        "source_name": source_name,
        "entity": canonical["entity"],
        "periods": canonical["periods"],
        "canonical_reference": reference,
        "available_data": list(derive_available_data(canonical)),
        "available_assumptions": sorted(canonical["assumptions"]),
        "mapping": {
            "package_id": package["package_id"],
            "profile_id": profile["profile_id"],
            "mapping_id": mapping["mapping_id"],
            "mapped_row_count": sum(
                item["status"] == "mapped" for item in mapping["row_mappings"]
            ),
            "unmapped_row_count": len(unmapped),
        },
        "warnings": warnings,
        "ready": True,
        "blockers": [],
    }
    return {
        **provisional,
        "source_id": f"fmrsrc_{digest(provisional)[:24]}",
        "source_sha256": digest(provisional),
    }


STATEMENT_CSV_COLUMNS = (
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
)


def statement_csv_template() -> bytes:
    rows = [
        ",".join(STATEMENT_CSV_COLUMNS),
        "company-a,Company A,SGD,2025-12-31,actual,income_statement,flow,4000,Revenue,1000000,gl:4000:2025",
        "company-a,Company A,SGD,2025-12-31,actual,income_statement,flow,5000,Operating costs,750000,gl:5000:2025",
        "company-a,Company A,SGD,2025-12-31,actual,balance_sheet,point_in_time,1000,Cash,150000,gl:1000:2025",
        "company-a,Company A,SGD,2025-12-31,actual,balance_sheet,point_in_time,2100,Debt,200000,gl:2100:2025",
    ]
    return ("\n".join(rows) + "\n").encode("utf-8")


__all__ = [
    "STATEMENT_CSV_COLUMNS",
    "WorkflowSourceStore",
    "compile_canonical_financial_data",
    "create_statement_csv_workflow_source",
    "derive_available_data",
    "statement_csv_template",
]
