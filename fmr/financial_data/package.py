from __future__ import annotations

import csv
import hashlib
import io
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from fmr.financial_data.common import (
    ALLOWED_BALANCE_TYPES,
    ALLOWED_PERIOD_TYPES,
    ALLOWED_STATEMENTS,
    CURRENCY_RE,
    PACKAGE_CONTROLS,
    PACKAGE_ID_RE,
    decimal_string,
    digest,
    is_sha256,
)

_REQUIRED_COLUMNS = {
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
    if reader.fieldnames is None or set(reader.fieldnames) != _REQUIRED_COLUMNS:
        raise ValueError("statement CSV columns do not match the required contract")

    entity: tuple[str, str, str] | None = None
    period_meta: dict[str, dict[str, str]] = {}
    grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    duplicate_keys: set[tuple[str, str, str, str, str, str]] = set()
    for line_number, raw in enumerate(reader, start=2):
        values = {
            key: (raw.get(key) or "").strip() for key in _REQUIRED_COLUMNS
        }
        if not all(
            values[key] for key in _REQUIRED_COLUMNS - {"account_code"}
        ):
            raise ValueError(
                f"statement CSV row {line_number} contains blank required fields"
            )
        current_entity = (
            values["entity_id"],
            values["entity_name"],
            values["currency"].upper(),
        )
        if entity is None:
            entity = current_entity
        elif current_entity != entity:
            raise ValueError(
                "statement CSV must contain exactly one entity and currency"
            )
        if not CURRENCY_RE.fullmatch(current_entity[2]):
            raise ValueError(
                f"statement CSV row {line_number} currency must be three uppercase letters"
            )
        try:
            date.fromisoformat(values["period_end"])
        except ValueError as exc:
            raise ValueError(
                f"statement CSV row {line_number} period_end must be YYYY-MM-DD"
            ) from exc
        if values["period_type"] not in ALLOWED_PERIOD_TYPES:
            raise ValueError(
                f"statement CSV row {line_number} period_type is invalid"
            )
        if values["statement_type"] not in ALLOWED_STATEMENTS:
            raise ValueError(
                f"statement CSV row {line_number} statement_type is invalid"
            )
        if values["balance_type"] not in ALLOWED_BALANCE_TYPES:
            raise ValueError(
                f"statement CSV row {line_number} balance_type is invalid"
            )
        if (
            values["statement_type"] in {"income_statement", "cash_flow"}
            and values["balance_type"] != "flow"
        ):
            raise ValueError(
                f"statement CSV row {line_number} must use flow balance_type"
            )
        if (
            values["statement_type"] == "balance_sheet"
            and values["balance_type"] != "point_in_time"
        ):
            raise ValueError(
                f"statement CSV row {line_number} must use point_in_time balance_type"
            )
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
            raise ValueError(
                f"statement CSV row {line_number} duplicates an account-period value"
            )
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
        item["values"].append(
            {"period_id": period_id, "amount": decimal_string(amount)}
        )
    if entity is None or not grouped:
        raise ValueError("statement CSV contains no data rows")

    periods = sorted(
        period_meta.values(),
        key=lambda item: (item["period_end"], item["period_type"]),
    )
    period_order = {
        item["period_id"]: index for index, item in enumerate(periods)
    }
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(
        sorted(
            grouped.values(),
            key=lambda row: (
                row["statement_type"],
                row["account_code"] or "",
                row["account_name"],
                row["source_ref"],
            ),
        ),
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
        "entity": {
            "entity_id": entity[0],
            "entity_name": entity[1],
            "currency": entity[2],
        },
        "periods": periods,
        "rows": rows,
        "controls": list(PACKAGE_CONTROLS),
    }
    payload = {
        **provisional,
        "package_id": f"fmrd_{digest(provisional)[:24]}",
    }
    issues = validate_financial_data_package(payload)
    if issues:
        raise ValueError(
            "compiled financial data package is invalid: " + "; ".join(issues)
        )
    return payload


def validate_financial_data_package(payload: Any) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("financial data package must be an object",)
    expected = {
        "contract_version",
        "package_id",
        "source",
        "entity",
        "periods",
        "rows",
        "controls",
    }
    if set(payload) != expected:
        issues.append("financial data package fields are invalid")
    if payload.get("contract_version") != "financial-data-package.v1":
        issues.append("unsupported contract_version")
    package_id = payload.get("package_id")
    if not isinstance(package_id, str) or not PACKAGE_ID_RE.fullmatch(package_id):
        issues.append("package_id is invalid")

    source = payload.get("source")
    if not isinstance(source, dict) or set(source) != {
        "kind",
        "filename",
        "sha256",
        "size_bytes",
    }:
        issues.append("source fields are invalid")
    elif (
        source.get("kind") != "statement_csv"
        or not isinstance(source.get("filename"), str)
        or not source.get("filename")
        or not is_sha256(source.get("sha256"))
        or not isinstance(source.get("size_bytes"), int)
        or source.get("size_bytes") <= 0
    ):
        issues.append("source metadata is invalid")

    entity = payload.get("entity")
    if not isinstance(entity, dict) or set(entity) != {
        "entity_id",
        "entity_name",
        "currency",
    }:
        issues.append("entity fields are invalid")
    elif (
        not all(
            isinstance(entity.get(key), str) and entity.get(key)
            for key in ("entity_id", "entity_name")
        )
        or not CURRENCY_RE.fullmatch(entity.get("currency", ""))
    ):
        issues.append("entity values are invalid")

    periods = payload.get("periods")
    period_ids: list[str] = []
    if not isinstance(periods, list) or not periods:
        issues.append("periods must be a non-empty array")
    else:
        for index, period in enumerate(periods):
            if not isinstance(period, dict) or set(period) != {
                "period_id",
                "period_end",
                "period_type",
            }:
                issues.append(f"periods[{index}] fields are invalid")
                continue
            period_ids.append(period.get("period_id"))
            try:
                date.fromisoformat(period.get("period_end", ""))
            except (TypeError, ValueError):
                issues.append(f"periods[{index}].period_end is invalid")
            if period.get("period_type") not in ALLOWED_PERIOD_TYPES:
                issues.append(f"periods[{index}].period_type is invalid")
            if period.get("period_id") != (
                f"{period.get('period_end')}:{period.get('period_type')}"
            ):
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
            if not isinstance(row, dict) or set(row) != {
                "row_id",
                "statement_type",
                "balance_type",
                "account_code",
                "account_name",
                "source_ref",
                "values",
            }:
                issues.append(f"rows[{index}] fields are invalid")
                continue
            row_ids.append(row.get("row_id"))
            if (
                row.get("statement_type") not in ALLOWED_STATEMENTS
                or row.get("balance_type") not in ALLOWED_BALANCE_TYPES
            ):
                issues.append(
                    f"rows[{index}] statement or balance type is invalid"
                )
            if (
                not isinstance(row.get("account_name"), str)
                or not row.get("account_name")
                or not isinstance(row.get("source_ref"), str)
                or not row.get("source_ref")
            ):
                issues.append(
                    f"rows[{index}] account_name and source_ref must be non-empty"
                )
            values = row.get("values")
            seen: set[str] = set()
            if not isinstance(values, list) or not values:
                issues.append(f"rows[{index}].values must be non-empty")
            else:
                for value_index, value in enumerate(values):
                    if not isinstance(value, dict) or set(value) != {
                        "period_id",
                        "amount",
                    }:
                        issues.append(
                            f"rows[{index}].values[{value_index}] fields are invalid"
                        )
                        continue
                    if value.get("period_id") not in allowed_periods:
                        issues.append(
                            f"rows[{index}].values[{value_index}].period_id is unknown"
                        )
                    if value.get("period_id") in seen:
                        issues.append(f"rows[{index}] repeats a period")
                    seen.add(value.get("period_id"))
                    try:
                        amount = Decimal(value.get("amount", ""))
                        if not amount.is_finite():
                            raise InvalidOperation
                    except (InvalidOperation, TypeError):
                        issues.append(
                            f"rows[{index}].values[{value_index}].amount is invalid"
                        )
        if len(row_ids) != len(set(row_ids)):
            issues.append("row IDs must be unique")

    if payload.get("controls") != list(PACKAGE_CONTROLS):
        issues.append("controls do not match the required package controls")
    if isinstance(package_id, str) and PACKAGE_ID_RE.fullmatch(package_id):
        candidate = dict(payload)
        candidate.pop("package_id", None)
        if package_id != f"fmrd_{digest(candidate)[:24]}":
            issues.append("package_id does not match payload")
    return tuple(dict.fromkeys(issues))


def _parse_decimal(value: str, line_number: int) -> Decimal:
    try:
        amount = Decimal(value.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(
            f"statement CSV row {line_number} amount is invalid"
        ) from exc
    if not amount.is_finite():
        raise ValueError(
            f"statement CSV row {line_number} amount must be finite"
        )
    return amount


__all__ = ["import_statement_csv", "validate_financial_data_package"]
