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
    validate_workbook_calculation_acceptance_payload,
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
