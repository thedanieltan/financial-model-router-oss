from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fmr.core import FAMILIES, ModelJob, route_job, routing_policy
from fmr.core.receipts import validate_execution_result
from fmr.execution import ExecutionOrchestrator, SqliteExecutionLedger
from fmr.provider_service import prepare_handoff
from fmr.registry import ProviderRegistry

PROVIDER_COMMANDS = {"discover-providers", "route-job", "prepare-handoff", "execute-job", "validate-job-result"}


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
    discover = commands.add_parser("discover-providers")
    discover.add_argument("--output")
    for name in ("route-job", "prepare-handoff"):
        command = commands.add_parser(name)
        command.add_argument("job")
        command.add_argument("--policy", default="default")
        command.add_argument("--output")
    execute = commands.add_parser("execute-job")
    execute.add_argument("handoff")
    execute.add_argument("--idempotency-key", required=True)
    execute.add_argument("--output-dir", default=".")
    execute.add_argument("--execution-mode", choices=("local", "remote", "handoff_only"))
    execute.add_argument("--receipt")
    validate = commands.add_parser("validate-job-result")
    validate.add_argument("result")
    validate.add_argument("--handoff", required=True)
    validate.add_argument("--output")
    return parser


def run_provider_command(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "discover-providers":
            registry = ProviderRegistry.builtins()
            _write({"providers": [item.to_dict() for item in registry.providers()], "model_families": [item.to_dict() for item in FAMILIES]}, args.output)
            return 0
        if args.command == "route-job":
            job = ModelJob.from_mapping(_load(args.job))
            _write(route_job(job, policy=routing_policy(args.policy)), args.output)
            return 0
        if args.command == "prepare-handoff":
            _write(prepare_handoff(_load(args.job), policy_name=args.policy), args.output)
            return 0
        if args.command == "execute-job":
            handoff = _load(args.handoff)
            output_directory = Path(args.output_dir)
            orchestrator = ExecutionOrchestrator(ledger=SqliteExecutionLedger(output_directory.parent / ".fmr-execution-ledger.sqlite3"))
            result = orchestrator.execute_request({
                "contract_version": "execution-request.v1", "handoff": handoff,
                "idempotency_key": args.idempotency_key,
                "execution_mode": args.execution_mode or handoff.get("execution_configuration", {}).get("mode"),
                "timeout_seconds": 120, "secret_references": [],
                "output_policy": {"mode": "specified_directory", "directory": str(output_directory), "overwrite": False, "publish": False},
            })
            _write(result, args.receipt)
            return 0 if result["state"] == "completed" else 2
        issues = validate_execution_result(_load(args.result), handoff=_load(args.handoff))
        _write({"valid": not issues, "issues": list(issues)}, args.output)
        return 0 if not issues else 2
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        _write({"valid": False, "error": str(exc)})
        return 2
