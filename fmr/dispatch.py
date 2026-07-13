from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from fmr.cli import main as legacy_main
from fmr.workbook import (
    compile_workbook_write_plan,
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
    if arguments and arguments[0] == "serve":
        return _serve_composed(arguments[1:])
    return legacy_main(arguments)
