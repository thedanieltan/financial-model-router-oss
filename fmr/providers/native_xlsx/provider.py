from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from fmr.data import validate_canonical_model_input


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_input(reference: dict[str, Any]) -> dict[str, Any]:
    path = reference.get("path")
    expected_hash = reference.get("sha256")
    if not isinstance(path, str) or not path or not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError("canonical model input reference requires path and sha256")
    data = Path(path).read_bytes()
    if _sha256(data) != expected_hash:
        raise ValueError("canonical model input hash mismatch")
    payload = json.loads(data)
    issues = validate_canonical_model_input(payload)
    if issues:
        raise ValueError("invalid canonical model input: " + "; ".join(issues))
    return payload


def validate_budget_workbook(path: str | os.PathLike[str]) -> dict[str, Any]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError('Native XLSX requires the "executor" package extra') from exc
    workbook = load_workbook(path, data_only=False, read_only=True)
    try:
        required = {"Inputs", "Budget Forecast", "Checks"}
        missing = sorted(required - set(workbook.sheetnames))
        formulas = 0
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                formulas += sum(isinstance(cell.value, str) and cell.value.startswith("=") for cell in row)
        issues = []
        if missing:
            issues.append("missing_sheets:" + ",".join(missing))
        if formulas == 0:
            issues.append("no_formulas")
        if not missing:
            forecast = workbook["Budget Forecast"]
            period_count = max(forecast.max_column - 1, 0)
            for column in _columns(period_count):
                expected = {2: f"=Inputs!{column}2", 3: f"=Inputs!{column}3", 4: f"={column}2-{column}3"}
                for row, formula in expected.items():
                    if forecast[f"{column}{row}"].value != formula:
                        issues.append(f"formula_mismatch:Budget Forecast!{column}{row}")
            expected_check = f"=COLUMNS('Budget Forecast'!B1:{_columns(period_count)[-1]}1)" if period_count else None
            if workbook["Checks"]["B2"].value != expected_check:
                issues.append("formula_mismatch:Checks!B2")
        return {"status": "passed" if not issues else "failed", "issues": issues, "sheet_count": len(workbook.sheetnames), "formula_count": formulas}
    finally:
        workbook.close()


def execute_budget_forecast_handoff(handoff: dict[str, Any], output_dir: str | os.PathLike[str]) -> dict[str, Any]:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError as exc:
        raise RuntimeError('Native XLSX requires the "executor" package extra') from exc
    if handoff.get("contract_version") != "provider-handoff.v1" or handoff.get("status") != "ready":
        raise ValueError("a ready provider-handoff.v1 is required")
    if handoff.get("provider", {}).get("provider_id") != "native-xlsx":
        raise ValueError("handoff is not assigned to Native XLSX")
    payload = handoff.get("provider_payload")
    if not isinstance(payload, dict) or payload.get("adapter_id") != "native-xlsx/generic-budget-forecast.v1":
        raise ValueError("unsupported Native XLSX adapter")
    model_input = _load_input(payload.get("canonical_financial_data", {}))
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / payload.get("output_filename", "budget-forecast.xlsx")
    if output.exists():
        raise ValueError("output path already exists")

    workbook = Workbook()
    inputs = workbook.active
    inputs.title = "Inputs"
    forecast = workbook.create_sheet("Budget Forecast")
    checks = workbook.create_sheet("Checks")
    periods = model_input["periods"]
    inputs.append(["Metric", *periods])
    statement = model_input["financial_statements"].get("income_statement", {})
    if "revenue" not in statement or "operating_costs" not in statement:
        raise ValueError("Native XLSX budget package requires revenue and operating_costs income-statement series")
    inputs.append(["Revenue", *[float(value) for value in statement["revenue"]]])
    inputs.append(["Operating costs", *[float(value) for value in statement["operating_costs"]]])
    forecast.append(["Metric", *periods])
    forecast.append(["Revenue"] + [f"=Inputs!{column}2" for column in _columns(len(periods))])
    forecast.append(["Operating costs"] + [f"=Inputs!{column}3" for column in _columns(len(periods))])
    forecast.append(["Operating profit"] + [f"={column}2-{column}3" for column in _columns(len(periods))])
    checks.append(["Check", "Status"])
    checks.append(["Period count", f"=COLUMNS('Budget Forecast'!B1:{_columns(len(periods))[-1]}1)"])
    for sheet in (inputs, forecast, checks):
        for cell in sheet[1]:
            cell.font = Font(bold=True)

    with tempfile.NamedTemporaryFile(prefix=".fmr-", suffix=".xlsx", dir=destination, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        workbook.save(temporary)
        workbook.close()
        validation = validate_budget_workbook(temporary)
        if validation["status"] != "passed":
            raise ValueError("Native XLSX output validation failed: " + "; ".join(validation["issues"]))
        data = temporary.read_bytes()
        os.replace(temporary, output)
    finally:
        workbook.close()
        temporary.unlink(missing_ok=True)
    return {
        "provider_receipt_version": "native-xlsx-receipt.v1",
        "status": "completed",
        "output_artifacts": [{"kind": "budget_forecast_workbook", "path": str(output), "sha256": _sha256(data), "size_bytes": len(data)}],
        "validation": validation,
        "controls": ["atomic_output", "input_hash_verified", "no_input_values_in_receipt", "output_reopened_and_validated"],
    }


def _columns(count: int) -> list[str]:
    result = []
    for number in range(2, count + 2):
        letters = ""
        value = number
        while value:
            value, remainder = divmod(value - 1, 26)
            letters = chr(65 + remainder) + letters
        result.append(letters)
    return result
