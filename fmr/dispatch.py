from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from fmr.cli import main as legacy_main
from fmr.workbook import (
    accept_calculated_workbook_bytes,
    calculate_and_accept_workbook_file,
    calculation_engine_status,
    compile_workbook_write_plan,
    execute_workbook_write_plan_file,
    validate_workbook_calculation_acceptance_payload,
    validate_workbook_execution_receipt_payload,
    validate_workbook_write_plan_payload,
)


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


def _write_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fmr")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser(
        "plan-writes",
        help="Compile a deterministic dry-run workbook-write-plan.v1 document",
    )
    plan.add_argument("realization_plan")
    plan.add_argument("write_context")
    plan.add_argument("--output")

    validate = subparsers.add_parser(
        "validate-write-plan",
        help="Validate and deterministically recompute workbook-write-plan.v1",
    )
    validate.add_argument("write_plan")
    validate.add_argument("--realization-plan", required=True)
    validate.add_argument("--write-context", required=True)
    return parser


def _executor_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fmr")
    subparsers = parser.add_subparsers(dest="command", required=True)

    execute = subparsers.add_parser(
        "execute-writes",
        help="Apply an accepted write plan to a copied XLSX workbook",
    )
    execute.add_argument("source_workbook")
    execute.add_argument("write_plan")
    execute.add_argument("--output", required=True)
    execute.add_argument("--receipt", required=True)

    validate = subparsers.add_parser(
        "validate-execution-receipt",
        help="Validate workbook-execution-receipt.v1",
    )
    validate.add_argument("receipt")
    validate.add_argument("--write-plan")
    return parser


def _calculation_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fmr")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser(
        "calculation-engine-status",
        help="Report whether a supported spreadsheet calculation engine is available",
    )
    status.add_argument("--engine")

    calculate = subparsers.add_parser(
        "calculate-output",
        help="Recalculate a populated XLSX workbook and validate its cached results",
    )
    calculate.add_argument("input_workbook")
    calculate.add_argument("write_plan")
    calculate.add_argument("execution_receipt")
    calculate.add_argument("--output", required=True)
    calculate.add_argument("--receipt", required=True)
    calculate.add_argument("--engine")
    calculate.add_argument("--timeout", type=int, default=120)

    accept = subparsers.add_parser(
        "accept-calculated-output",
        help="Validate a workbook recalculated by an external spreadsheet engine",
    )
    accept.add_argument("input_workbook")
    accept.add_argument("calculated_workbook")
    accept.add_argument("write_plan")
    accept.add_argument("execution_receipt")
    accept.add_argument("--receipt", required=True)
    accept.add_argument("--engine-name", required=True)
    accept.add_argument("--engine-version", required=True)

    validate = subparsers.add_parser(
        "validate-calculation-acceptance",
        help="Validate workbook-calculation-acceptance.v1",
    )
    validate.add_argument("acceptance")
    validate.add_argument("--write-plan")
    validate.add_argument("--execution-receipt")
    return parser


def _run_write_command(argv: list[str]) -> int:
    args = _write_parser().parse_args(argv)
    try:
        realization_plan = _load(args.realization_plan)
        write_context = _load(args.write_context)
        if args.command == "plan-writes":
            write_plan = compile_workbook_write_plan(realization_plan, write_context)
            issues = validate_workbook_write_plan_payload(
                write_plan,
                realization_plan=realization_plan,
                write_context=write_context,
            )
            if issues:
                raise ValueError("compiled write plan is invalid: " + "; ".join(issues))
            _write(write_plan, args.output)
            return 0
        issues = validate_workbook_write_plan_payload(
            _load(args.write_plan),
            realization_plan=realization_plan,
            write_context=write_context,
        )
        _write({"valid": not issues, "issues": list(issues)})
        return 0 if not issues else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _write({"valid": False, "error": str(exc)})
        return 2


def _run_executor_command(argv: list[str]) -> int:
    args = _executor_parser().parse_args(argv)
    try:
        if args.command == "execute-writes":
            write_plan = _load(args.write_plan)
            receipt = execute_workbook_write_plan_file(
                args.source_workbook,
                output_path=args.output,
                write_plan=write_plan,
            )
            issues = validate_workbook_execution_receipt_payload(
                receipt,
                write_plan=write_plan,
            )
            if issues:
                Path(args.output).unlink(missing_ok=True)
                raise ValueError("execution receipt is invalid: " + "; ".join(issues))
            _write(receipt, args.receipt)
            return 0
        write_plan = _load(args.write_plan) if args.write_plan else None
        issues = validate_workbook_execution_receipt_payload(
            _load(args.receipt),
            write_plan=write_plan,
        )
        _write({"valid": not issues, "issues": list(issues)})
        return 0 if not issues else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _write({"valid": False, "error": str(exc)})
        return 2


def _run_calculation_command(argv: list[str]) -> int:
    args = _calculation_parser().parse_args(argv)
    try:
        if args.command == "calculation-engine-status":
            payload = calculation_engine_status(args.engine)
            _write(payload)
            return 0 if payload["available"] else 2
        if args.command == "calculate-output":
            write_plan = _load(args.write_plan)
            execution_receipt = _load(args.execution_receipt)
            receipt = calculate_and_accept_workbook_file(
                args.input_workbook,
                output_path=args.output,
                write_plan=write_plan,
                execution_receipt=execution_receipt,
                engine_executable=args.engine,
                timeout_seconds=args.timeout,
            )
            _write(receipt, args.receipt)
            return 0 if receipt["status"] == "passed" else 2
        if args.command == "accept-calculated-output":
            write_plan = _load(args.write_plan)
            execution_receipt = _load(args.execution_receipt)
            receipt = accept_calculated_workbook_bytes(
                Path(args.input_workbook).read_bytes(),
                Path(args.calculated_workbook).read_bytes(),
                input_filename=Path(args.input_workbook).name,
                output_filename=Path(args.calculated_workbook).name,
                write_plan=write_plan,
                execution_receipt=execution_receipt,
                engine={
                    "name": args.engine_name,
                    "version": args.engine_version,
                    "adapter": "external-calculation.v1",
                },
            )
            _write(receipt, args.receipt)
            return 0 if receipt["status"] == "passed" else 2
        write_plan = _load(args.write_plan) if args.write_plan else None
        execution_receipt = (
            _load(args.execution_receipt) if args.execution_receipt else None
        )
        issues = validate_workbook_calculation_acceptance_payload(
            _load(args.acceptance),
            write_plan=write_plan,
            execution_receipt=execution_receipt,
        )
        _write({"valid": not issues, "issues": list(issues)})
        return 0 if not issues else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _write({"valid": False, "error": str(exc)})
        return 2


def _serve_composed(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="fmr serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        _write({"valid": False, "error": "port must be between 1 and 65535"})
        return 2
    try:
        import uvicorn
    except ImportError:
        _write({
            "valid": False,
            "error": 'Developer UI dependencies are missing. Install with: pip install -e ".[dev-ui]"',
        })
        return 2
    uvicorn.run("fmr.api.composed:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in {"plan-writes", "validate-write-plan"}:
        return _run_write_command(arguments)
    if arguments and arguments[0] in {"execute-writes", "validate-execution-receipt"}:
        return _run_executor_command(arguments)
    if arguments and arguments[0] in {
        "calculation-engine-status",
        "calculate-output",
        "accept-calculated-output",
        "validate-calculation-acceptance",
    }:
        return _run_calculation_command(arguments)
    if arguments and arguments[0] == "serve":
        return _serve_composed(arguments[1:])
    return legacy_main(arguments)
