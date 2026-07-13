from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

from fmr.workbook.calculation import (
    CalculationEngine,
    WorkbookCalculationResult,
    _digest,
    _load_openpyxl,
    _run_engine,
    accept_calculated_workbook_bytes as _accept_calculated_workbook_bytes,
    calculation_engine_status,
    discover_calculation_engine,
    validate_workbook_calculation_acceptance_payload as _validate_acceptance,
)
from fmr.workbook.executor import _cells

_BOOLEAN_CALL_RE = re.compile(r"\b(TRUE|FALSE)\(\)", re.IGNORECASE)
_COLOUR_TOKEN_RE = re.compile(r"\[([A-Za-z]+)\]")


def _normalise_formula(value: Any) -> str | None:
    if not isinstance(value, str) or not value.startswith("="):
        return None
    compact = "".join(value.split()).upper().replace(";", ",")
    return _BOOLEAN_CALL_RE.sub(lambda match: match.group(1).upper(), compact)


def _formulas_equivalent(expected: Any, actual: Any) -> bool:
    expected_normalised = _normalise_formula(expected)
    actual_normalised = _normalise_formula(actual)
    return (
        expected_normalised is not None
        and actual_normalised is not None
        and expected_normalised == actual_normalised
    )


def _normalise_number_format(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalised = _COLOUR_TOKEN_RE.sub(
        lambda match: f"[{match.group(1).upper()}]",
        value,
    )
    for character in ("(", ")", "-"):
        normalised = normalised.replace(f"\\{character}", character)
    return normalised


def _number_formats_equivalent(
    expected: Any,
    actual: Any,
    *,
    semantic_type: Any,
) -> bool:
    expected_normalised = _normalise_number_format(expected)
    actual_normalised = _normalise_number_format(actual)
    if (
        expected_normalised is not None
        and actual_normalised is not None
        and expected_normalised == actual_normalised
    ):
        return True
    if semantic_type == "boolean":
        return str(expected).upper() in {"GENERAL", "BOOLEAN"} and str(
            actual
        ).upper() in {"GENERAL", "BOOLEAN"}
    return False


def _verify_records(workbook, write_plan: dict[str, Any]) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    verified: list[str] = []
    failures: list[dict[str, str]] = []
    input_cell_count = 0
    populated_input_cell_count = 0

    for phase in write_plan["phases"]:
        for record in phase["records"]:
            record_id = record["record_id"]
            issue_code: str | None = None
            try:
                sheet_name = record["sheet_name"]
                if sheet_name not in workbook.sheetnames:
                    issue_code = "sheet_missing"
                elif record["write_kind"] == "ensure_sheet":
                    expected_position = record["payload"]["position"]
                    actual_position = workbook.sheetnames.index(sheet_name) + 1
                    if actual_position != expected_position:
                        issue_code = "sheet_position_mismatch"
                else:
                    worksheet = workbook[sheet_name]
                    cells = list(_cells(worksheet, record["coordinate"]))
                    if record["write_kind"] == "reserve_input":
                        input_cell_count += len(cells)
                        populated_input_cell_count += sum(
                            cell.value not in (None, "") for cell in cells
                        )
                    elif record["write_kind"] == "write_value":
                        if (
                            len(cells) != 1
                            or cells[0].value != record["payload"]["value"]
                        ):
                            issue_code = "value_mismatch"
                    elif record["write_kind"] == "write_formula":
                        if len(cells) != 1 or not _formulas_equivalent(
                            record["payload"]["formula"],
                            cells[0].value,
                        ):
                            issue_code = "formula_mismatch"
                    elif record["write_kind"] == "apply_style":
                        style = record["payload"]["style"]
                        expected_locked = style["role_style"]["protection"][
                            "locked"
                        ]
                        expected_format = style["number_format"]["code"]
                        semantic_type = style.get("semantic_type")
                        for cell in cells:
                            if cell.protection.locked != expected_locked:
                                issue_code = "protection_mismatch"
                                break
                            if expected_format != "source" and not (
                                _number_formats_equivalent(
                                    expected_format,
                                    cell.number_format,
                                    semantic_type=semantic_type,
                                )
                            ):
                                issue_code = "number_format_mismatch"
                                break
                    else:
                        issue_code = "write_kind_unsupported"
            except (KeyError, TypeError, ValueError):
                issue_code = issue_code or "record_verification_error"

            if issue_code is None:
                verified.append(record_id)
            else:
                failures.append(
                    {"record_id": record_id, "issue_code": issue_code}
                )

    if input_cell_count != populated_input_cell_count:
        failures.append(
            {
                "record_id": "reserved_inputs_incomplete",
                "issue_code": "reserved_inputs_incomplete",
            }
        )
    return {
        "verified_record_ids": verified,
        "failed_record_ids": list(
            dict.fromkeys(item["record_id"] for item in failures)
        ),
        "failures": failures,
        "verified_record_count": len(verified),
        "input_cell_count": input_cell_count,
        "populated_input_cell_count": populated_input_cell_count,
    }


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
    """Accept recalculation only when both input and output preserve the plan.

    Formula comparison permits only engine-neutral syntax changes: whitespace,
    case, comma/semicolon separators and TRUE/FALSE with optional parentheses.
    Number-format comparison permits only colour-token case and LibreOffice
    escaping of parentheses or hyphens, plus General/BOOLEAN equivalence for
    boolean cells. No other formula or style drift is accepted.
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

    input_workbook = _load_openpyxl(input_bytes, data_only=False)
    output_workbook = _load_openpyxl(calculated_bytes, data_only=False)
    try:
        input_verification = _verify_records(input_workbook, write_plan)
        output_verification = _verify_records(output_workbook, write_plan)
    finally:
        input_workbook.close()
        output_workbook.close()

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
    scoped_failures = [
        {
            "scope": scope,
            "record_id": failure["record_id"],
            "issue_code": failure["issue_code"],
        }
        for scope, verification in (
            ("input", input_verification),
            ("output", output_verification),
        )
        for failure in verification["failures"]
    ]
    combined = {
        "verified_record_ids": verified_both,
        "failed_record_ids": list(
            dict.fromkeys(
                f"{item['scope']}:{item['record_id']}"
                for item in scoped_failures
            )
        ),
        "failures": scoped_failures,
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
        expected_fields = {
            "verified_record_ids",
            "failed_record_ids",
            "failures",
            "verified_record_count",
            "input_cell_count",
            "populated_input_cell_count",
        }
        if set(immutable) != expected_fields:
            issues.append("immutable_verification fields are invalid")
        verified = immutable.get("verified_record_ids")
        failed = immutable.get("failed_record_ids")
        failures = immutable.get("failures")
        if isinstance(verified, list):
            if len(verified) != len(set(verified)):
                issues.append("immutable verified_record_ids contain duplicates")
            if immutable.get("verified_record_count") != len(verified):
                issues.append(
                    "immutable verified_record_count does not match verified_record_ids"
                )
        if isinstance(failed, list) and len(failed) != len(set(failed)):
            issues.append("immutable failed_record_ids contain duplicates")
        if not isinstance(failures, list):
            issues.append("immutable failures must be an array")
        else:
            expected_failed_ids: list[str] = []
            for index, failure in enumerate(failures):
                if not isinstance(failure, dict) or set(failure) != {
                    "scope",
                    "record_id",
                    "issue_code",
                }:
                    issues.append(f"immutable failures[{index}] fields are invalid")
                    continue
                if failure.get("scope") not in {"input", "output"}:
                    issues.append(f"immutable failures[{index}].scope is invalid")
                if not isinstance(failure.get("record_id"), str) or not failure.get(
                    "record_id"
                ):
                    issues.append(
                        f"immutable failures[{index}].record_id is invalid"
                    )
                if not isinstance(failure.get("issue_code"), str) or not failure.get(
                    "issue_code"
                ):
                    issues.append(
                        f"immutable failures[{index}].issue_code is invalid"
                    )
                if isinstance(failure.get("scope"), str) and isinstance(
                    failure.get("record_id"), str
                ):
                    expected_failed_ids.append(
                        f"{failure['scope']}:{failure['record_id']}"
                    )
            if isinstance(failed, list) and failed != list(
                dict.fromkeys(expected_failed_ids)
            ):
                issues.append("immutable failed_record_ids do not match failures")
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
            failures = immutable.get("failures")
            if isinstance(verified, list) and any(
                item not in expected_record_set for item in verified
            ):
                issues.append("immutable verification references unknown records")
            failed_records = {
                item.get("record_id")
                for item in failures or []
                if isinstance(item, dict)
                and item.get("record_id") != "reserved_inputs_incomplete"
            }
            unknown = failed_records - expected_record_set
            if unknown:
                issues.append("immutable failures reference unknown records")
            accounted = set(verified or []) | (failed_records & expected_record_set)
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
