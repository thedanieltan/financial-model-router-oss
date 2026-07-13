from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

from fmr.workbook.executor import (
    WorkbookExecutionResult,
    _EXECUTION_CONTROLS,
    _apply_record,
    _digest,
    _load_workbook,
    _record_state,
    _request_recalculation,
    _save_workbook,
    _verify_records,
    validate_workbook_execution_receipt_payload,
)
from fmr.workbook.inspect import inspect_workbook_bytes
from fmr.workbook.write_plan_public import validate_workbook_write_plan_payload


def execute_workbook_write_plan_bytes(
    source_bytes: bytes,
    *,
    filename: str,
    output_filename: str,
    write_plan: dict[str, Any],
) -> WorkbookExecutionResult:
    if not isinstance(source_bytes, bytes) or not source_bytes:
        raise ValueError("source workbook bytes must be non-empty")
    if not filename.lower().endswith(".xlsx"):
        raise ValueError("source workbook must use the .xlsx extension")
    if not output_filename.lower().endswith(".xlsx"):
        raise ValueError("output workbook must use the .xlsx extension")

    issues = validate_workbook_write_plan_payload(write_plan)
    if issues:
        raise ValueError("invalid workbook write plan: " + "; ".join(issues))
    if not write_plan.get("ready_for_executor"):
        raise ValueError("workbook write plan is blocked")

    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    source = write_plan["source"]
    if source_sha256 != source["sha256"]:
        raise ValueError("source workbook hash does not match the write plan")
    if len(source_bytes) != source["size_bytes"]:
        raise ValueError("source workbook size does not match the write plan")

    source_map = inspect_workbook_bytes(source_bytes, filename=filename)
    if source_map.external_links_detected:
        raise ValueError("source workbook contains external links")
    unsupported_findings = [
        item
        for item in source_map.findings
        if item.startswith("unsupported_feature:")
        or item.startswith("unsupported_sheet_type:")
    ]
    if unsupported_findings:
        raise ValueError(
            "source workbook contains unsupported features: "
            + "; ".join(unsupported_findings)
        )

    workbook = _load_workbook(source_bytes)
    record_receipts: list[dict[str, Any]] = []
    try:
        for phase in write_plan["phases"]:
            for record in phase["records"]:
                before = _record_state(workbook, record)
                _apply_record(workbook, record)
                after = _record_state(workbook, record)
                record_receipts.append(
                    {
                        "record_id": record["record_id"],
                        "sequence": record["sequence"],
                        "write_kind": record["write_kind"],
                        "sheet_name": record["sheet_name"],
                        "coordinate": record["coordinate"],
                        "status": "applied",
                        "cell_count": after["cell_count"],
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
        raise ValueError("executor produced an output workbook with external links")

    reopened = _load_workbook(output_bytes)
    try:
        verification = _verify_records(reopened, write_plan)
    finally:
        reopened.close()
    if verification["failed_record_ids"]:
        raise ValueError(
            "output workbook verification failed for records: "
            + ", ".join(verification["failed_record_ids"])
        )

    output_sha256 = hashlib.sha256(output_bytes).hexdigest()
    provisional = {
        "contract_version": "workbook-execution-receipt.v1",
        "write_plan_id": write_plan["write_plan_id"],
        "write_plan_sha256": _digest(write_plan),
        "source": {
            "filename": filename,
            "sha256": source_sha256,
            "size_bytes": len(source_bytes),
        },
        "output": {
            "filename": output_filename,
            "sha256": output_sha256,
            "size_bytes": len(output_bytes),
        },
        "status": "completed",
        "records": record_receipts,
        "verification": {
            **verification,
            "source_hash_unchanged": hashlib.sha256(source_bytes).hexdigest() == source_sha256,
            "output_reopened": True,
            "external_links_detected": output_map.external_links_detected,
            "formula_calculation_deferred": True,
        },
        "controls": list(_EXECUTION_CONTROLS),
    }
    receipt = {
        **provisional,
        "execution_id": f"fmre_{_digest(provisional)[:24]}",
    }
    return WorkbookExecutionResult(output_bytes=output_bytes, receipt=receipt)


def execute_workbook_write_plan_file(
    source_path: str | os.PathLike[str],
    *,
    output_path: str | os.PathLike[str],
    write_plan: dict[str, Any],
) -> dict[str, Any]:
    source = Path(source_path)
    output = Path(output_path)
    if source.resolve() == output.resolve():
        raise ValueError("output path must differ from the source path")
    if source.suffix.lower() != ".xlsx" or output.suffix.lower() != ".xlsx":
        raise ValueError("source and output paths must use the .xlsx extension")
    if output.exists():
        raise ValueError("output path already exists")
    if not source.is_file():
        raise ValueError("source workbook does not exist")

    source_bytes = source.read_bytes()
    result = execute_workbook_write_plan_bytes(
        source_bytes,
        filename=source.name,
        output_filename=output.name,
        write_plan=write_plan,
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


__all__ = [
    "WorkbookExecutionResult",
    "execute_workbook_write_plan_bytes",
    "execute_workbook_write_plan_file",
    "validate_workbook_execution_receipt_payload",
]
