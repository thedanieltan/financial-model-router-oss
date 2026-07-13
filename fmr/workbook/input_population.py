from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fmr.workbook.executor import (
    _cells,
    _digest,
    _load_workbook,
    _record_state,
    _request_recalculation,
    _save_workbook,
    _verify_record,
)
from fmr.workbook.executor_public import validate_workbook_execution_receipt_payload
from fmr.workbook.inspect import inspect_workbook_bytes
from fmr.workbook.write_plan_public import validate_workbook_write_plan_payload

_INPUT_SET_ID_RE = re.compile(r"^fmri_[0-9a-f]{24}$")
_POPULATION_ID_RE = re.compile(r"^fmrp_[0-9a-f]{24}$")
_RANGE_RE = re.compile(
    r"^([A-Z]{1,3})([1-9][0-9]*)(?::([A-Z]{1,3})([1-9][0-9]*))?$"
)
_INPUT_SET_CONTROLS = (
    "complete_reserved_input_coverage",
    "execution_receipt_pinned",
    "explicit_record_binding",
    "finite_values_only",
    "formulas_forbidden",
    "source_provenance_declared",
    "write_plan_pinned",
)
_POPULATION_CONTROLS = (
    "atomic_output_publish",
    "execution_output_hash_verified",
    "failed_output_removed",
    "immutable_records_verified",
    "input_set_pinned",
    "no_source_overwrite",
    "output_reopened_and_verified",
    "receipt_excludes_input_values",
    "reserved_inputs_only",
    "write_plan_pinned",
)
_FORBIDDEN_RECEIPT_KEYS = {
    "value",
    "values",
    "input_value",
    "before_value",
    "after_value",
    "cell_value",
}


@dataclass(frozen=True)
class WorkbookInputPopulationResult:
    output_bytes: bytes
    receipt: dict[str, Any]


def compile_workbook_input_set_from_csv(
    csv_bytes: bytes,
    *,
    source_name: str,
    write_plan: dict[str, Any],
    execution_receipt: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(csv_bytes, bytes) or not csv_bytes:
        raise ValueError("CSV input bytes must be non-empty")
    if not isinstance(source_name, str) or not source_name:
        raise ValueError("CSV source_name must be non-empty")
    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV input must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text))
    expected_fields = {"record_id", "cell_index", "value_type", "value", "source_ref"}
    if reader.fieldnames is None or set(reader.fieldnames) != expected_fields:
        raise ValueError(
            "CSV columns must be record_id, cell_index, value_type, value and source_ref"
        )

    grouped: dict[str, list[tuple[int, str, Any, str]]] = {}
    for row_number, row in enumerate(reader, start=2):
        record_id = (row.get("record_id") or "").strip()
        value_type = (row.get("value_type") or "").strip().lower()
        source_ref = (row.get("source_ref") or "").strip()
        try:
            cell_index = int((row.get("cell_index") or "").strip())
        except ValueError as exc:
            raise ValueError(f"CSV row {row_number} cell_index must be an integer") from exc
        if cell_index < 1:
            raise ValueError(f"CSV row {row_number} cell_index must be positive")
        raw_value = row.get("value") or ""
        value = _parse_csv_value(raw_value, value_type, row_number)
        if not record_id:
            raise ValueError(f"CSV row {row_number} record_id must be non-empty")
        if not source_ref:
            raise ValueError(f"CSV row {row_number} source_ref must be non-empty")
        grouped.setdefault(record_id, []).append(
            (cell_index, value_type, value, source_ref)
        )

    bindings: list[dict[str, Any]] = []
    for record in _reserved_records(write_plan):
        record_id = record["record_id"]
        rows = grouped.pop(record_id, None)
        if rows is None:
            raise ValueError(f"CSV is missing reserved input record {record_id}")
        rows.sort(key=lambda item: item[0])
        expected_indices = list(range(1, len(rows) + 1))
        if [item[0] for item in rows] != expected_indices:
            raise ValueError(f"CSV cell_index values are not contiguous for {record_id}")
        value_types = {item[1] for item in rows}
        source_refs = {item[3] for item in rows}
        if len(value_types) != 1:
            raise ValueError(f"CSV value_type is inconsistent for {record_id}")
        if len(source_refs) != 1:
            raise ValueError(f"CSV source_ref is inconsistent for {record_id}")
        bindings.append(
            {
                "record_id": record_id,
                "value_type": rows[0][1],
                "values": [item[2] for item in rows],
                "source_ref": rows[0][3],
            }
        )
    if grouped:
        raise ValueError(
            "CSV contains unknown or non-input record IDs: " + ", ".join(sorted(grouped))
        )

    provisional = {
        "contract_version": "workbook-input-set.v1",
        "write_plan_id": write_plan.get("write_plan_id"),
        "write_plan_sha256": _digest(write_plan),
        "execution_id": execution_receipt.get("execution_id"),
        "execution_receipt_sha256": _digest(execution_receipt),
        "source": {
            "kind": "csv",
            "reference": source_name,
            "sha256": hashlib.sha256(csv_bytes).hexdigest(),
            "size_bytes": len(csv_bytes),
        },
        "bindings": bindings,
        "controls": list(_INPUT_SET_CONTROLS),
    }
    payload = {
        **provisional,
        "input_set_id": f"fmri_{_digest(provisional)[:24]}",
    }
    issues = validate_workbook_input_set_payload(
        payload,
        write_plan=write_plan,
        execution_receipt=execution_receipt,
    )
    if issues:
        raise ValueError("compiled input set is invalid: " + "; ".join(issues))
    return payload


def validate_workbook_input_set_payload(
    payload: Any,
    *,
    write_plan: dict[str, Any] | None = None,
    execution_receipt: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("input set must be an object",)
    allowed = {
        "contract_version",
        "input_set_id",
        "write_plan_id",
        "write_plan_sha256",
        "execution_id",
        "execution_receipt_sha256",
        "source",
        "bindings",
        "controls",
    }
    extras = sorted(set(payload) - allowed)
    if extras:
        issues.append(f"input set contains undeclared fields: {extras}")
    if payload.get("contract_version") != "workbook-input-set.v1":
        issues.append("unsupported contract_version")
    input_set_id = payload.get("input_set_id")
    if not isinstance(input_set_id, str) or not _INPUT_SET_ID_RE.fullmatch(input_set_id):
        issues.append("input_set_id is invalid")
    for field in ("write_plan_sha256", "execution_receipt_sha256"):
        if not _is_sha256(payload.get(field)):
            issues.append(f"{field} must be a SHA-256 hex string")
    source = payload.get("source")
    if not isinstance(source, dict):
        issues.append("source must be an object")
    else:
        expected = {"kind", "reference", "sha256", "size_bytes"}
        if set(source) != expected:
            issues.append("source fields are invalid")
        if source.get("kind") not in {"csv", "json", "manual", "system"}:
            issues.append("source.kind is invalid")
        if not isinstance(source.get("reference"), str) or not source.get("reference"):
            issues.append("source.reference must be non-empty")
        if source.get("sha256") is not None and not _is_sha256(source.get("sha256")):
            issues.append("source.sha256 must be null or a SHA-256 hex string")
        if source.get("size_bytes") is not None and (
            not isinstance(source.get("size_bytes"), int)
            or source.get("size_bytes") < 0
        ):
            issues.append("source.size_bytes must be null or a non-negative integer")

    bindings = payload.get("bindings")
    actual_ids: list[str] = []
    if not isinstance(bindings, list):
        issues.append("bindings must be an array")
    else:
        for index, binding in enumerate(bindings):
            context = f"bindings[{index}]"
            if not isinstance(binding, dict):
                issues.append(f"{context} must be an object")
                continue
            expected = {"record_id", "value_type", "values", "source_ref"}
            if set(binding) != expected:
                issues.append(f"{context} fields are invalid")
            record_id = binding.get("record_id")
            if not isinstance(record_id, str) or not record_id:
                issues.append(f"{context}.record_id must be non-empty")
            else:
                actual_ids.append(record_id)
            value_type = binding.get("value_type")
            if value_type not in {"number", "boolean"}:
                issues.append(f"{context}.value_type is invalid")
            values = binding.get("values")
            if not isinstance(values, list) or not values:
                issues.append(f"{context}.values must be a non-empty array")
            else:
                for value_index, value in enumerate(values):
                    if not _valid_value(value, value_type):
                        issues.append(
                            f"{context}.values[{value_index}] does not match value_type"
                        )
            if not isinstance(binding.get("source_ref"), str) or not binding.get(
                "source_ref"
            ):
                issues.append(f"{context}.source_ref must be non-empty")
        if len(actual_ids) != len(set(actual_ids)):
            issues.append("binding record IDs must be unique")

    if payload.get("controls") != list(_INPUT_SET_CONTROLS):
        issues.append("controls do not match the required control set")

    if write_plan is not None:
        plan_issues = validate_workbook_write_plan_payload(write_plan)
        if plan_issues:
            issues.append("source write plan is invalid")
        if payload.get("write_plan_id") != write_plan.get("write_plan_id"):
            issues.append("write_plan_id does not match the source write plan")
        if payload.get("write_plan_sha256") != _digest(write_plan):
            issues.append("write_plan_sha256 does not match the source write plan")
        expected_records = _reserved_records(write_plan)
        expected_ids = [record["record_id"] for record in expected_records]
        if actual_ids != expected_ids:
            issues.append("binding order and coverage do not match reserved inputs")
        if isinstance(bindings, list):
            records = {record["record_id"]: record for record in expected_records}
            for index, binding in enumerate(bindings):
                if not isinstance(binding, dict):
                    continue
                record = records.get(binding.get("record_id"))
                values = binding.get("values")
                if record is not None and isinstance(values, list):
                    expected_count = _coordinate_cell_count(record["coordinate"])
                    if len(values) != expected_count:
                        issues.append(
                            f"bindings[{index}].values count does not match reserved range"
                        )

    if execution_receipt is not None:
        receipt_issues = validate_workbook_execution_receipt_payload(
            execution_receipt,
            write_plan=write_plan,
        )
        if receipt_issues:
            issues.append("source execution receipt is invalid")
        if payload.get("execution_id") != execution_receipt.get("execution_id"):
            issues.append("execution_id does not match the source execution receipt")
        if payload.get("execution_receipt_sha256") != _digest(execution_receipt):
            issues.append(
                "execution_receipt_sha256 does not match the source execution receipt"
            )

    if isinstance(input_set_id, str) and _INPUT_SET_ID_RE.fullmatch(input_set_id):
        candidate = dict(payload)
        candidate.pop("input_set_id", None)
        if input_set_id != f"fmri_{_digest(candidate)[:24]}":
            issues.append("input_set_id does not match payload")
    return tuple(dict.fromkeys(issues))


def populate_workbook_inputs_bytes(
    executed_bytes: bytes,
    *,
    filename: str,
    output_filename: str,
    write_plan: dict[str, Any],
    execution_receipt: dict[str, Any],
    input_set: dict[str, Any],
) -> WorkbookInputPopulationResult:
    if not isinstance(executed_bytes, bytes) or not executed_bytes:
        raise ValueError("executed workbook bytes must be non-empty")
    if not filename.lower().endswith(".xlsx") or not output_filename.lower().endswith(
        ".xlsx"
    ):
        raise ValueError("input and output workbook names must use .xlsx")
    plan_issues = validate_workbook_write_plan_payload(write_plan)
    if plan_issues:
        raise ValueError("invalid workbook write plan: " + "; ".join(plan_issues))
    receipt_issues = validate_workbook_execution_receipt_payload(
        execution_receipt,
        write_plan=write_plan,
    )
    if receipt_issues:
        raise ValueError(
            "invalid workbook execution receipt: " + "; ".join(receipt_issues)
        )
    input_issues = validate_workbook_input_set_payload(
        input_set,
        write_plan=write_plan,
        execution_receipt=execution_receipt,
    )
    if input_issues:
        raise ValueError("invalid workbook input set: " + "; ".join(input_issues))

    source_sha256 = hashlib.sha256(executed_bytes).hexdigest()
    if source_sha256 != execution_receipt["output"]["sha256"]:
        raise ValueError("executed workbook hash does not match the execution receipt")
    if len(executed_bytes) != execution_receipt["output"]["size_bytes"]:
        raise ValueError("executed workbook size does not match the execution receipt")

    source_map = inspect_workbook_bytes(executed_bytes, filename=filename)
    if source_map.external_links_detected:
        raise ValueError("executed workbook contains external links")
    unsupported = [
        item
        for item in source_map.findings
        if item.startswith("unsupported_feature:")
        or item.startswith("unsupported_sheet_type:")
    ]
    if unsupported:
        raise ValueError(
            "executed workbook contains unsupported features: " + "; ".join(unsupported)
        )

    workbook = _load_workbook(executed_bytes)
    records: list[dict[str, Any]] = []
    try:
        failed_source_records = _verify_source_records(workbook, write_plan)
        if failed_source_records:
            raise ValueError(
                "executed workbook does not match the write plan: "
                + ", ".join(failed_source_records)
            )
        binding_by_id = {
            binding["record_id"]: binding for binding in input_set["bindings"]
        }
        for record in _reserved_records(write_plan):
            binding = binding_by_id[record["record_id"]]
            worksheet = workbook[record["sheet_name"]]
            cells = list(_cells(worksheet, record["coordinate"]))
            before = _record_state(workbook, record)
            for cell, value in zip(cells, binding["values"], strict=True):
                if cell.value not in (None, ""):
                    raise ValueError(
                        f"reserved input is already populated: {record['record_id']}"
                    )
                cell.value = value
            after = _record_state(workbook, record)
            records.append(
                {
                    "record_id": record["record_id"],
                    "sheet_name": record["sheet_name"],
                    "coordinate": record["coordinate"],
                    "value_type": binding["value_type"],
                    "cell_count": len(cells),
                    "source_ref_sha256": hashlib.sha256(
                        binding["source_ref"].encode("utf-8")
                    ).hexdigest(),
                    "status": "populated",
                    "before_sha256": _digest(before),
                    "after_sha256": _digest(after),
                }
            )
        _request_recalculation(workbook)
        output_bytes = _save_workbook(workbook)
    finally:
        workbook.close()

    output_map = inspect_workbook_bytes(output_bytes, filename=output_filename)
    if output_map.external_links_detected:
        raise ValueError("input population produced external links")
    reopened = _load_workbook(output_bytes)
    try:
        verification = _verify_populated_output(reopened, write_plan, input_set)
    finally:
        reopened.close()
    if verification["failed_record_ids"]:
        raise ValueError(
            "populated workbook verification failed for records: "
            + ", ".join(verification["failed_record_ids"])
        )

    provisional = {
        "contract_version": "workbook-input-population-receipt.v1",
        "input_set_id": input_set["input_set_id"],
        "input_set_sha256": _digest(input_set),
        "write_plan_id": write_plan["write_plan_id"],
        "write_plan_sha256": _digest(write_plan),
        "execution_id": execution_receipt["execution_id"],
        "execution_receipt_sha256": _digest(execution_receipt),
        "source": {
            "filename": filename,
            "sha256": source_sha256,
            "size_bytes": len(executed_bytes),
        },
        "output": {
            "filename": output_filename,
            "sha256": hashlib.sha256(output_bytes).hexdigest(),
            "size_bytes": len(output_bytes),
        },
        "status": "completed",
        "records": records,
        "verification": {
            **verification,
            "source_hash_matches_execution_output": True,
            "output_reopened": True,
            "external_links_detected": False,
        },
        "controls": list(_POPULATION_CONTROLS),
    }
    receipt = {
        **provisional,
        "population_id": f"fmrp_{_digest(provisional)[:24]}",
    }
    receipt_issues = validate_workbook_input_population_receipt_payload(
        receipt,
        input_set=input_set,
        write_plan=write_plan,
        execution_receipt=execution_receipt,
    )
    if receipt_issues:
        raise ValueError(
            "generated population receipt is invalid: " + "; ".join(receipt_issues)
        )
    return WorkbookInputPopulationResult(output_bytes=output_bytes, receipt=receipt)


def populate_workbook_inputs_file(
    input_path: str | os.PathLike[str],
    *,
    output_path: str | os.PathLike[str],
    write_plan: dict[str, Any],
    execution_receipt: dict[str, Any],
    input_set: dict[str, Any],
) -> dict[str, Any]:
    source = Path(input_path)
    output = Path(output_path)
    if source.resolve() == output.resolve():
        raise ValueError("population output path must differ from the input path")
    if source.suffix.lower() != ".xlsx" or output.suffix.lower() != ".xlsx":
        raise ValueError("input and output paths must use the .xlsx extension")
    if not source.is_file():
        raise ValueError("executed workbook does not exist")
    if output.exists():
        raise ValueError("population output path already exists")

    result = populate_workbook_inputs_bytes(
        source.read_bytes(),
        filename=source.name,
        output_filename=output.name,
        write_plan=write_plan,
        execution_receipt=execution_receipt,
        input_set=input_set,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(result.output_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    except Exception:
        temporary.unlink(missing_ok=True)
        output.unlink(missing_ok=True)
        raise
    return result.receipt


def validate_workbook_input_population_receipt_payload(
    payload: Any,
    *,
    input_set: dict[str, Any] | None = None,
    write_plan: dict[str, Any] | None = None,
    execution_receipt: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("input population receipt must be an object",)
    allowed = {
        "contract_version",
        "population_id",
        "input_set_id",
        "input_set_sha256",
        "write_plan_id",
        "write_plan_sha256",
        "execution_id",
        "execution_receipt_sha256",
        "source",
        "output",
        "status",
        "records",
        "verification",
        "controls",
    }
    extras = sorted(set(payload) - allowed)
    if extras:
        issues.append(f"population receipt contains undeclared fields: {extras}")
    if payload.get("contract_version") != "workbook-input-population-receipt.v1":
        issues.append("unsupported contract_version")
    population_id = payload.get("population_id")
    if not isinstance(population_id, str) or not _POPULATION_ID_RE.fullmatch(
        population_id
    ):
        issues.append("population_id is invalid")
    if payload.get("status") != "completed":
        issues.append("status must be completed")
    for field in (
        "input_set_sha256",
        "write_plan_sha256",
        "execution_receipt_sha256",
    ):
        if not _is_sha256(payload.get(field)):
            issues.append(f"{field} must be a SHA-256 hex string")
    for name in ("source", "output"):
        _validate_file(payload.get(name), name, issues)

    records = payload.get("records")
    actual_ids: list[str] = []
    if not isinstance(records, list):
        issues.append("records must be an array")
    else:
        expected_fields = {
            "record_id",
            "sheet_name",
            "coordinate",
            "value_type",
            "cell_count",
            "source_ref_sha256",
            "status",
            "before_sha256",
            "after_sha256",
        }
        for index, record in enumerate(records):
            context = f"records[{index}]"
            if not isinstance(record, dict) or set(record) != expected_fields:
                issues.append(f"{context} fields are invalid")
                continue
            actual_ids.append(record.get("record_id"))
            if record.get("value_type") not in {"number", "boolean"}:
                issues.append(f"{context}.value_type is invalid")
            if record.get("status") != "populated":
                issues.append(f"{context}.status must be populated")
            if not isinstance(record.get("cell_count"), int) or record.get(
                "cell_count"
            ) <= 0:
                issues.append(f"{context}.cell_count must be positive")
            for field in ("source_ref_sha256", "before_sha256", "after_sha256"):
                if not _is_sha256(record.get(field)):
                    issues.append(f"{context}.{field} is invalid")
        if len(actual_ids) != len(set(actual_ids)):
            issues.append("receipt record IDs must be unique")

    verification = payload.get("verification")
    if not isinstance(verification, dict):
        issues.append("verification must be an object")
    else:
        expected = {
            "populated_record_count",
            "populated_cell_count",
            "immutable_record_count",
            "failed_record_ids",
            "source_hash_matches_execution_output",
            "output_reopened",
            "external_links_detected",
        }
        if set(verification) != expected:
            issues.append("verification fields are invalid")
        for field in (
            "populated_record_count",
            "populated_cell_count",
            "immutable_record_count",
        ):
            if not isinstance(verification.get(field), int) or verification.get(
                field
            ) < 0:
                issues.append(f"verification.{field} must be non-negative")
        if verification.get("failed_record_ids") != []:
            issues.append("verification.failed_record_ids must be empty")
        for field in ("source_hash_matches_execution_output", "output_reopened"):
            if verification.get(field) is not True:
                issues.append(f"verification.{field} must be true")
        if verification.get("external_links_detected") is not False:
            issues.append("verification.external_links_detected must be false")
        if isinstance(records, list):
            if verification.get("populated_record_count") != len(records):
                issues.append(
                    "verification.populated_record_count does not match records"
                )
            cell_count = sum(
                record.get("cell_count", 0)
                for record in records
                if isinstance(record, dict)
                and isinstance(record.get("cell_count"), int)
            )
            if verification.get("populated_cell_count") != cell_count:
                issues.append(
                    "verification.populated_cell_count does not match records"
                )

    if payload.get("controls") != list(_POPULATION_CONTROLS):
        issues.append("controls do not match the required control set")
    if _contains_forbidden_key(payload):
        issues.append("population receipt contains input values")

    if input_set is not None:
        if payload.get("input_set_id") != input_set.get("input_set_id"):
            issues.append("input_set_id does not match the source input set")
        if payload.get("input_set_sha256") != _digest(input_set):
            issues.append("input_set_sha256 does not match the source input set")
        if isinstance(records, list):
            expected_ids = [
                binding.get("record_id")
                for binding in input_set.get("bindings", [])
                if isinstance(binding, dict)
            ]
            if actual_ids != expected_ids:
                issues.append("receipt record order does not match the input set")
    if write_plan is not None:
        if payload.get("write_plan_id") != write_plan.get("write_plan_id"):
            issues.append("write_plan_id does not match the source write plan")
        if payload.get("write_plan_sha256") != _digest(write_plan):
            issues.append("write_plan_sha256 does not match the source write plan")
        if isinstance(verification, dict):
            immutable_count = sum(
                1
                for phase in write_plan.get("phases", [])
                for record in phase.get("records", [])
                if record.get("write_kind") != "reserve_input"
            )
            if verification.get("immutable_record_count") != immutable_count:
                issues.append(
                    "verification.immutable_record_count does not match write plan"
                )
    if execution_receipt is not None:
        if payload.get("execution_id") != execution_receipt.get("execution_id"):
            issues.append(
                "execution_id does not match the source execution receipt"
            )
        if payload.get("execution_receipt_sha256") != _digest(execution_receipt):
            issues.append(
                "execution_receipt_sha256 does not match the source receipt"
            )
        source = payload.get("source")
        expected_output = execution_receipt.get("output")
        if isinstance(source, dict) and isinstance(expected_output, dict):
            if source.get("sha256") != expected_output.get("sha256"):
                issues.append(
                    "population source hash does not match execution output"
                )
            if source.get("size_bytes") != expected_output.get("size_bytes"):
                issues.append(
                    "population source size does not match execution output"
                )

    if isinstance(population_id, str) and _POPULATION_ID_RE.fullmatch(population_id):
        candidate = dict(payload)
        candidate.pop("population_id", None)
        if population_id != f"fmrp_{_digest(candidate)[:24]}":
            issues.append("population_id does not match payload")
    return tuple(dict.fromkeys(issues))


def _verify_source_records(workbook, write_plan: dict[str, Any]) -> list[str]:  # type: ignore[no-untyped-def]
    failed: list[str] = []
    for phase in write_plan["phases"]:
        for record in phase["records"]:
            try:
                _verify_record(workbook, record)
            except ValueError:
                failed.append(record["record_id"])
    return failed


def _verify_populated_output(
    workbook,
    write_plan: dict[str, Any],
    input_set: dict[str, Any],
) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    binding_by_id = {
        binding["record_id"]: binding for binding in input_set["bindings"]
    }
    failed: list[str] = []
    immutable_count = 0
    populated_cell_count = 0
    for phase in write_plan["phases"]:
        for record in phase["records"]:
            try:
                if record["write_kind"] == "reserve_input":
                    binding = binding_by_id[record["record_id"]]
                    cells = list(
                        _cells(
                            workbook[record["sheet_name"]],
                            record["coordinate"],
                        )
                    )
                    if len(cells) != len(binding["values"]):
                        raise ValueError("input shape mismatch")
                    if any(
                        cell.value != expected
                        for cell, expected in zip(
                            cells,
                            binding["values"],
                            strict=True,
                        )
                    ):
                        raise ValueError("input value mismatch")
                    populated_cell_count += len(cells)
                else:
                    _verify_record(workbook, record)
                    immutable_count += 1
            except (KeyError, TypeError, ValueError):
                failed.append(record["record_id"])
    return {
        "populated_record_count": len(_reserved_records(write_plan)),
        "populated_cell_count": populated_cell_count,
        "immutable_record_count": immutable_count,
        "failed_record_ids": failed,
    }


def _reserved_records(write_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        record
        for phase in write_plan.get("phases", [])
        for record in phase.get("records", [])
        if isinstance(record, dict) and record.get("write_kind") == "reserve_input"
    ]


def _parse_csv_value(raw: str, value_type: str, row_number: int) -> Any:
    if value_type == "boolean":
        lowered = raw.strip().lower()
        if lowered not in {"true", "false"}:
            raise ValueError(f"CSV row {row_number} boolean value must be true or false")
        return lowered == "true"
    if value_type == "number":
        text = raw.strip()
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError(f"CSV row {row_number} number value is invalid") from exc
        if not math.isfinite(value):
            raise ValueError(f"CSV row {row_number} number value must be finite")
        if value.is_integer() and "e" not in text.lower() and "." not in text:
            return int(value)
        return value
    raise ValueError(f"CSV row {row_number} value_type must be number or boolean")


def _valid_value(value: Any, value_type: Any) -> bool:
    if value_type == "boolean":
        return isinstance(value, bool)
    if value_type == "number":
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
        )
    return False


def _coordinate_cell_count(coordinate: str) -> int:
    match = _RANGE_RE.fullmatch(coordinate or "")
    if not match:
        raise ValueError("coordinate is invalid")
    start_col, start_row, end_col, end_row = match.groups()
    end_col = end_col or start_col
    end_row = end_row or start_row
    return (
        (_column_number(end_col) - _column_number(start_col) + 1)
        * (int(end_row) - int(start_row) + 1)
    )


def _column_number(label: str) -> int:
    value = 0
    for character in label:
        value = value * 26 + (ord(character) - ord("A") + 1)
    return value


def _validate_file(value: Any, name: str, issues: list[str]) -> None:
    if not isinstance(value, dict):
        issues.append(f"{name} must be an object")
        return
    if set(value) != {"filename", "sha256", "size_bytes"}:
        issues.append(f"{name} fields are invalid")
    if not isinstance(value.get("filename"), str) or not value.get("filename"):
        issues.append(f"{name}.filename must be non-empty")
    if not _is_sha256(value.get("sha256")):
        issues.append(f"{name}.sha256 must be a SHA-256 hex string")
    if not isinstance(value.get("size_bytes"), int) or value.get("size_bytes") <= 0:
        issues.append(f"{name}.size_bytes must be positive")


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key in _FORBIDDEN_RECEIPT_KEYS or _contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


__all__ = [
    "WorkbookInputPopulationResult",
    "compile_workbook_input_set_from_csv",
    "populate_workbook_inputs_bytes",
    "populate_workbook_inputs_file",
    "validate_workbook_input_population_receipt_payload",
    "validate_workbook_input_set_payload",
]
