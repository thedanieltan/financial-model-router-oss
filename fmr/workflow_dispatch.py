from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fmr.workflow import compile_workflow, execute_workflow, workflow_rerun_plan
from fmr.workflow_acceptance import run_workflow_acceptance_corpus


WORKFLOW_COMMANDS = {
    "compile-workflow",
    "execute-workflow",
    "plan-workflow-rerun",
    "run-workflow-acceptance",
}


def _load(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def _write(value: Any, output: str | None = None) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if output:
        Path(output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fmr")
    commands = parser.add_subparsers(dest="command", required=True)
    compile_command = commands.add_parser("compile-workflow")
    compile_command.add_argument("request")
    compile_command.add_argument("--output")
    execute_command = commands.add_parser("execute-workflow")
    execute_command.add_argument("plan")
    execute_command.add_argument("--idempotency-key", required=True)
    execute_command.add_argument("--output-dir", required=True)
    execute_command.add_argument("--approvals")
    execute_command.add_argument("--receipt")
    rerun_command = commands.add_parser("plan-workflow-rerun")
    rerun_command.add_argument("plan")
    rerun_command.add_argument("--changed-input", action="append", required=True)
    rerun_command.add_argument("--output")
    acceptance_command = commands.add_parser("run-workflow-acceptance")
    acceptance_command.add_argument("corpus")
    acceptance_command.add_argument("--require-practitioner", action="store_true")
    acceptance_command.add_argument("--output")
    return parser


def run_workflow_command(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "compile-workflow":
            _write(compile_workflow(_load(args.request)), args.output)
            return 0
        if args.command == "execute-workflow":
            approvals = _load(args.approvals) if args.approvals else None
            result = execute_workflow(
                _load(args.plan),
                idempotency_key=args.idempotency_key,
                output_dir=args.output_dir,
                approvals=approvals,
            )
            _write(result, args.receipt)
            return 0 if result["state"] == "completed" else 2
        if args.command == "plan-workflow-rerun":
            _write(workflow_rerun_plan(_load(args.plan), args.changed_input), args.output)
            return 0
        result = run_workflow_acceptance_corpus(_load(args.corpus))
        _write(result, args.output)
        accepted = result["production_status"] == "accepted" if args.require_practitioner else result["implementation_status"] == "passed"
        return 0 if accepted else 2
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        _write({"valid": False, "error": str(exc)})
        return 2


__all__ = ["WORKFLOW_COMMANDS", "run_workflow_command"]
