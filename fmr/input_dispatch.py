from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fmr.providers.native_xlsx.workbook import (
    compile_workbook_input_set_from_csv,
    populate_workbook_inputs_file,
    validate_input_population_calculation_link,
    validate_workbook_input_population_receipt_payload,
    validate_workbook_input_set_payload,
)

INPUT_COMMANDS = {
    "compile-input-set-csv",
    "validate-input-set",
    "populate-inputs",
    "validate-input-population-receipt",
    "validate-input-calculation-link",
}


def _load(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def _write(payload: dict[str, Any], output: str | None = None) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output:
        Path(output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fmr")
    subparsers = parser.add_subparsers(dest="command", required=True)

    compile_csv = subparsers.add_parser(
        "compile-input-set-csv",
        help="Compile UTF-8 CSV rows into workbook-input-set.v1",
    )
    compile_csv.add_argument("csv_file")
    compile_csv.add_argument("write_plan")
    compile_csv.add_argument("execution_receipt")
    compile_csv.add_argument("--output")

    validate_set = subparsers.add_parser(
        "validate-input-set",
        help="Validate workbook-input-set.v1",
    )
    validate_set.add_argument("input_set")
    validate_set.add_argument("--write-plan")
    validate_set.add_argument("--execution-receipt")

    populate = subparsers.add_parser(
        "populate-inputs",
        help="Populate reserved input ranges in an executed workbook copy",
    )
    populate.add_argument("input_workbook")
    populate.add_argument("input_set")
    populate.add_argument("write_plan")
    populate.add_argument("execution_receipt")
    populate.add_argument("--output", required=True)
    populate.add_argument("--receipt", required=True)

    validate_receipt = subparsers.add_parser(
        "validate-input-population-receipt",
        help="Validate workbook-input-population-receipt.v1",
    )
    validate_receipt.add_argument("receipt")
    validate_receipt.add_argument("--input-set")
    validate_receipt.add_argument("--write-plan")
    validate_receipt.add_argument("--execution-receipt")

    validate_link = subparsers.add_parser(
        "validate-input-calculation-link",
        help="Validate the hash chain from input population into calculation acceptance",
    )
    validate_link.add_argument("population_receipt")
    validate_link.add_argument("calculation_acceptance")
    return parser


def run_input_command(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "compile-input-set-csv":
            payload = compile_workbook_input_set_from_csv(
                Path(args.csv_file).read_bytes(),
                source_name=Path(args.csv_file).name,
                write_plan=_load(args.write_plan),
                execution_receipt=_load(args.execution_receipt),
            )
            _write(payload, args.output)
            return 0
        if args.command == "validate-input-set":
            issues = validate_workbook_input_set_payload(
                _load(args.input_set),
                write_plan=_load(args.write_plan) if args.write_plan else None,
                execution_receipt=(
                    _load(args.execution_receipt)
                    if args.execution_receipt
                    else None
                ),
            )
            _write({"valid": not issues, "issues": list(issues)})
            return 0 if not issues else 2
        if args.command == "populate-inputs":
            input_set = _load(args.input_set)
            write_plan = _load(args.write_plan)
            execution_receipt = _load(args.execution_receipt)
            receipt = populate_workbook_inputs_file(
                args.input_workbook,
                output_path=args.output,
                write_plan=write_plan,
                execution_receipt=execution_receipt,
                input_set=input_set,
            )
            issues = validate_workbook_input_population_receipt_payload(
                receipt,
                input_set=input_set,
                write_plan=write_plan,
                execution_receipt=execution_receipt,
            )
            if issues:
                Path(args.output).unlink(missing_ok=True)
                raise ValueError(
                    "input population receipt is invalid: " + "; ".join(issues)
                )
            _write(receipt, args.receipt)
            return 0
        if args.command == "validate-input-population-receipt":
            issues = validate_workbook_input_population_receipt_payload(
                _load(args.receipt),
                input_set=_load(args.input_set) if args.input_set else None,
                write_plan=_load(args.write_plan) if args.write_plan else None,
                execution_receipt=(
                    _load(args.execution_receipt)
                    if args.execution_receipt
                    else None
                ),
            )
            _write({"valid": not issues, "issues": list(issues)})
            return 0 if not issues else 2
        issues = validate_input_population_calculation_link(
            _load(args.population_receipt),
            _load(args.calculation_acceptance),
        )
        _write({"valid": not issues, "issues": list(issues)})
        return 0 if not issues else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _write({"valid": False, "error": str(exc)})
        return 2


__all__ = ["INPUT_COMMANDS", "run_input_command"]
