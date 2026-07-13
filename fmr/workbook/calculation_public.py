from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from fmr.workbook.calculation import (
    CalculationEngine,
    WorkbookCalculationResult,
    _digest,
    _load_openpyxl,
    _run_engine,
    _verify_input_records,
    accept_calculated_workbook_bytes as _accept_calculated_workbook_bytes,
    calculation_engine_status,
    discover_calculation_engine,
    validate_workbook_calculation_acceptance_payload as _validate_acceptance,
)


def accept_calculated_workbook_bytes(
    input_bytes: bytes,
    calculated_bytes: bytes,
    *,
    input_filename: str,
    output_filename: str,
    write_plan: dict[str, Any],
    execution_receipt: dict[str, Any],
    engine: dict[str, Any],
) -> dict[str, Any]:
    """Accept a recalculated workbook only when input and output preserve the plan.

    The base validator proves that user edits are limited to reserved input cells and
    that calculated formula caches are complete. This public boundary additionally
    verifies that the calculation engine did not alter generated labels, formulas,
    styles, protection, sheet setup or populated input values.
    """
    acceptance = _accept_calculated_workbook_bytes(
        input_bytes,
        calculated_bytes,
        input_filename=input_filename,
        output_filename=output_filename,
        write_plan=write_plan,
        execution_receipt=execution_receipt,
        engine=engine,
    )

    output_workbook = _load_openpyxl(calculated_bytes, data_only=False)
    try:
        output_verification = _verify_input_records(output_workbook, write_plan)
    finally:
        output_workbook.close()

    input_verification = acceptance["immutable_verification"]
    input_failed = list(input_verification["failed_record_ids"])
    output_failed = list(output_verification["failed_record_ids"])
    input_verified = set(input_verification["verified_record_ids"])
    output_verified = set(output_verification["verified_record_ids"])

    ordered_record_ids = [
        record["record_id"]
        for phase in write_plan["phases"]
        for record in phase["records"]
    ]
    verified_both = [
        record_id
        for record_id in ordered_record_ids
        if record_id in input_verified and record_id in output_verified
    ]
    combined_failures = [
        *(f"input:{record_id}" for record_id in input_failed),
        *(f"output:{record_id}" for record_id in output_failed),
    ]
    combined = {
        "verified_record_ids": verified_both,
        "failed_record_ids": list(dict.fromkeys(combined_failures)),
        "verified_record_count": len(verified_both),
        "input_cell_count": input_verification["input_cell_count"],
        "populated_input_cell_count": input_verification[
            "populated_input_cell_count"
        ],
    }
    acceptance["immutable_verification"] = combined
    acceptance["summary"]["immutable_record_count"] = len(verified_both)
    acceptance["summary"]["immutable_failure_count"] = len(
        combined["failed_record_ids"]
    )
    failure_count = (
        acceptance["summary"]["immutable_failure_count"]
        + acceptance["summary"]["planned_formula_failure_count"]
        + acceptance["summary"]["workbook_formula_error_count"]
        + acceptance["summary"]["missing_cached_value_count"]
    )
    acceptance["status"] = "passed" if failure_count == 0 else "failed"
    candidate = dict(acceptance)
    candidate.pop("acceptance_id", None)
    acceptance["acceptance_id"] = f"fmrc_{_digest(candidate)[:24]}"
    return acceptance


def validate_workbook_calculation_acceptance_payload(
    payload: Any,
    *,
    write_plan: dict[str, Any] | None = None,
    execution_receipt: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    issues = list(
        _validate_acceptance(
            payload,
            write_plan=write_plan,
            execution_receipt=execution_receipt,
        )
    )
    if not isinstance(payload, dict):
        return tuple(dict.fromkeys(issues))

    summary = payload.get("summary")
    immutable = payload.get("immutable_verification")
    formula_checks = payload.get("formula_checks")
    formula_scan = payload.get("workbook_formula_scan")

    if isinstance(immutable, dict):
        verified = immutable.get("verified_record_ids")
        failed = immutable.get("failed_record_ids")
        if isinstance(verified, list):
            if len(verified) != len(set(verified)):
                issues.append("immutable verified_record_ids contain duplicates")
            if immutable.get("verified_record_count") != len(verified):
                issues.append(
                    "immutable verified_record_count does not match verified_record_ids"
                )
        if isinstance(failed, list) and len(failed) != len(set(failed)):
            issues.append("immutable failed_record_ids contain duplicates")
        if isinstance(summary, dict):
            if summary.get("immutable_record_count") != immutable.get(
                "verified_record_count"
            ):
                issues.append(
                    "summary immutable_record_count does not match verification"
                )
            if isinstance(failed, list) and summary.get(
                "immutable_failure_count"
            ) != len(failed):
                issues.append(
                    "summary immutable_failure_count does not match verification"
                )
            if summary.get("input_cell_count") != immutable.get(
                "input_cell_count"
            ):
                issues.append("summary input_cell_count does not match verification")
            if summary.get("populated_input_cell_count") != immutable.get(
                "populated_input_cell_count"
            ):
                issues.append(
                    "summary populated_input_cell_count does not match verification"
                )

    if isinstance(formula_checks, list) and isinstance(summary, dict):
        failed_formula_count = sum(
            1
            for item in formula_checks
            if isinstance(item, dict) and item.get("status") == "failed"
        )
        if summary.get("planned_formula_count") != len(formula_checks):
            issues.append("summary planned_formula_count does not match checks")
        if summary.get("planned_formula_failure_count") != failed_formula_count:
            issues.append(
                "summary planned_formula_failure_count does not match checks"
            )

    if isinstance(formula_scan, dict) and isinstance(summary, dict):
        for summary_field, scan_field in (
            ("workbook_formula_count", "formula_count"),
            ("workbook_formula_error_count", "error_count"),
            ("missing_cached_value_count", "missing_cached_value_count"),
        ):
            if summary.get(summary_field) != formula_scan.get(scan_field):
                issues.append(
                    f"summary {summary_field} does not match workbook formula scan"
                )

    if write_plan is not None and isinstance(write_plan, dict):
        expected_records = [
            record["record_id"]
            for phase in write_plan.get("phases", [])
            if isinstance(phase, dict)
            for record in phase.get("records", [])
            if isinstance(record, dict) and isinstance(record.get("record_id"), str)
        ]
        expected_record_set = set(expected_records)
        if isinstance(immutable, dict):
            verified = immutable.get("verified_record_ids")
            failed = immutable.get("failed_record_ids")
            if isinstance(verified, list) and any(
                item not in expected_record_set for item in verified
            ):
                issues.append("immutable verification references unknown records")
            if isinstance(failed, list):
                raw_failures = {
                    item.split(":", 1)[1]
                    if isinstance(item, str) and ":" in item
                    else item
                    for item in failed
                }
                unknown = raw_failures - expected_record_set - {
                    "reserved_inputs_incomplete"
                }
                if unknown:
                    issues.append("immutable failures reference unknown records")
                accounted = set(verified or []) | (
                    raw_failures & expected_record_set
                )
                if accounted != expected_record_set:
                    issues.append(
                        "immutable verification does not account for every write record"
                    )
        expected_formula_ids = [
            record["record_id"]
            for phase in write_plan.get("phases", [])
            if isinstance(phase, dict)
            for record in phase.get("records", [])
            if isinstance(record, dict)
            and record.get("write_kind") == "write_formula"
            and isinstance(record.get("record_id"), str)
        ]
        if isinstance(formula_checks, list):
            actual_formula_ids = [
                item.get("record_id")
                for item in formula_checks
                if isinstance(item, dict)
            ]
            if actual_formula_ids != expected_formula_ids:
                issues.append(
                    "formula checks do not match ordered write-plan formula records"
                )

    return tuple(dict.fromkeys(issues))


def calculate_and_accept_workbook_bytes(
    input_bytes: bytes,
    *,
    input_filename: str,
    output_filename: str,
    write_plan: dict[str, Any],
    execution_receipt: dict[str, Any],
    engine_executable: str | None = None,
    timeout_seconds: int = 120,
) -> WorkbookCalculationResult:
    engine = discover_calculation_engine(engine_executable)
    output_bytes, process = _run_engine(
        input_bytes,
        input_filename=input_filename,
        engine=engine,
        timeout_seconds=timeout_seconds,
    )
    receipt = accept_calculated_workbook_bytes(
        input_bytes,
        output_bytes,
        input_filename=input_filename,
        output_filename=output_filename,
        write_plan=write_plan,
        execution_receipt=execution_receipt,
        engine={
            **engine.to_dict(),
            "return_code": process["return_code"],
            "stdout_sha256": process["stdout_sha256"],
            "stderr_sha256": process["stderr_sha256"],
        },
    )
    return WorkbookCalculationResult(output_bytes=output_bytes, receipt=receipt)


def calculate_and_accept_workbook_file(
    input_path: str | os.PathLike[str],
    *,
    output_path: str | os.PathLike[str],
    write_plan: dict[str, Any],
    execution_receipt: dict[str, Any],
    engine_executable: str | None = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    source = Path(input_path)
    output = Path(output_path)
    if source.resolve() == output.resolve():
        raise ValueError("calculated output path must differ from the input path")
    if source.suffix.lower() != ".xlsx" or output.suffix.lower() != ".xlsx":
        raise ValueError("input and output paths must use the .xlsx extension")
    if not source.is_file():
        raise ValueError("input workbook does not exist")
    if output.exists():
        raise ValueError("calculated output path already exists")

    result = calculate_and_accept_workbook_bytes(
        source.read_bytes(),
        input_filename=source.name,
        output_filename=output.name,
        write_plan=write_plan,
        execution_receipt=execution_receipt,
        engine_executable=engine_executable,
        timeout_seconds=timeout_seconds,
    )
    if result.receipt["status"] != "passed":
        return result.receipt

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


__all__ = [
    "CalculationEngine",
    "WorkbookCalculationResult",
    "accept_calculated_workbook_bytes",
    "calculate_and_accept_workbook_bytes",
    "calculate_and_accept_workbook_file",
    "calculation_engine_status",
    "discover_calculation_engine",
    "validate_workbook_calculation_acceptance_payload",
]
