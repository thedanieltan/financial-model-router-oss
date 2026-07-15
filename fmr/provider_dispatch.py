from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fmr.core import FAMILIES, ModelJob, create_model_intent, create_scope_confirmation, route_job, routing_policy
from fmr.core.receipts import validate_execution_result
from fmr.execution import ExecutionOrchestrator, ManagedArtifactRetention, SqliteExecutionLedger
from fmr.provider_service import prepare_handoff
from fmr.registry import ProviderRegistry
from fmr.organization import OrganizationPolicy, route_organization_job
from fmr.qualification import qualify_local_release
from fmr.acceptance import run_acceptance_corpus
from fmr.scoping_evidence import apply_workbook_scope_evidence, derive_workbook_scope_evidence
from fmr.scoping_service import answer_scope_question, assess_model_intent, compile_confirmed_scope
from fmr.scoping_acceptance import run_guided_scoping_acceptance_corpus

PROVIDER_COMMANDS = {
    "backup-execution-ledger",
    "answer-scope-question",
    "apply-workbook-scope-evidence",
    "assess-scope",
    "compile-scoped-job",
    "confirm-scope",
    "create-model-intent",
    "derive-workbook-scope-evidence",
    "discover-providers",
    "execute-job",
    "operations-status",
    "prepare-handoff",
    "prune-execution-artifacts",
    "qualify-release",
    "recover-executions",
    "route-job",
    "validate-job-result",
    "run-acceptance-corpus",
    "run-guided-scoping-acceptance",
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
    discover = commands.add_parser("discover-providers")
    discover.add_argument("--output")
    create_intent = commands.add_parser("create-model-intent")
    create_intent.add_argument("intent")
    create_intent.add_argument("--output")
    assess_scope = commands.add_parser("assess-scope")
    assess_scope.add_argument("intent")
    assess_scope.add_argument("--output")
    answer_scope = commands.add_parser("answer-scope-question")
    answer_scope.add_argument("intent")
    answer_scope.add_argument("--question", required=True)
    answer_scope.add_argument("--answer", required=True)
    answer_scope.add_argument("--output")
    confirm_scope = commands.add_parser("confirm-scope")
    confirm_scope.add_argument("assessment")
    confirm_scope.add_argument("--family", required=True)
    confirm_scope.add_argument("--acknowledge", action="append", default=[])
    confirm_scope.add_argument("--output")
    compile_scope = commands.add_parser("compile-scoped-job")
    compile_scope.add_argument("assessment")
    compile_scope.add_argument("confirmation")
    compile_scope.add_argument("--input-references")
    compile_scope.add_argument("--output")
    derive_evidence = commands.add_parser("derive-workbook-scope-evidence")
    derive_evidence.add_argument("workbook_map")
    derive_evidence.add_argument("--output")
    apply_evidence = commands.add_parser("apply-workbook-scope-evidence")
    apply_evidence.add_argument("intent")
    apply_evidence.add_argument("evidence")
    apply_evidence.add_argument("workbook_map")
    apply_evidence.add_argument("--output")
    for name in ("route-job", "prepare-handoff"):
        command = commands.add_parser(name)
        command.add_argument("job")
        command.add_argument("--policy", default="default")
        command.add_argument("--organization-policy")
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
    status = commands.add_parser("operations-status")
    status.add_argument("--ledger", required=True)
    status.add_argument("--stale-after", type=int, default=300)
    status.add_argument("--output")
    recover = commands.add_parser("recover-executions")
    recover.add_argument("--ledger", required=True)
    recover.add_argument("--stale-after", type=int, required=True)
    recover.add_argument("--output")
    backup = commands.add_parser("backup-execution-ledger")
    backup.add_argument("--ledger", required=True)
    backup.add_argument("destination")
    backup.add_argument("--output")
    prune = commands.add_parser("prune-execution-artifacts")
    prune.add_argument("--ledger", required=True)
    prune.add_argument("--managed-output-root", required=True)
    prune.add_argument("--older-than", type=int, required=True)
    prune.add_argument("--apply", action="store_true")
    prune.add_argument("--output")
    qualify = commands.add_parser("qualify-release")
    qualify.add_argument("--deployment-evidence")
    qualify.add_argument("--require-production", action="store_true")
    qualify.add_argument("--output")
    acceptance = commands.add_parser("run-acceptance-corpus")
    acceptance.add_argument("corpus")
    acceptance.add_argument("--require-practitioner", action="store_true")
    acceptance.add_argument("--output")
    scoping_acceptance = commands.add_parser("run-guided-scoping-acceptance")
    scoping_acceptance.add_argument("corpus")
    scoping_acceptance.add_argument("--require-practitioner", action="store_true")
    scoping_acceptance.add_argument("--output")
    return parser


def run_provider_command(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "discover-providers":
            registry = ProviderRegistry.builtins()
            _write({"providers": [item.to_dict() for item in registry.providers()], "model_families": [item.to_dict() for item in FAMILIES]}, args.output)
            return 0
        if args.command == "create-model-intent":
            _write(create_model_intent(_load(args.intent)), args.output)
            return 0
        if args.command == "assess-scope":
            _write(assess_model_intent(_load(args.intent)), args.output)
            return 0
        if args.command == "answer-scope-question":
            _write(answer_scope_question(_load(args.intent), args.question, args.answer), args.output)
            return 0
        if args.command == "confirm-scope":
            _write(create_scope_confirmation(_load(args.assessment), selected_family=args.family, acknowledged_limitations=args.acknowledge), args.output)
            return 0
        if args.command == "compile-scoped-job":
            references = _load(args.input_references) if args.input_references else None
            _write(compile_confirmed_scope(_load(args.assessment), _load(args.confirmation), input_references=references), args.output)
            return 0
        if args.command == "derive-workbook-scope-evidence":
            _write(derive_workbook_scope_evidence(_load(args.workbook_map)), args.output)
            return 0
        if args.command == "apply-workbook-scope-evidence":
            _write(apply_workbook_scope_evidence(_load(args.intent), _load(args.evidence), workbook_map=_load(args.workbook_map)), args.output)
            return 0
        if args.command == "route-job":
            raw_job = _load(args.job)
            if args.organization_policy:
                organization = OrganizationPolicy.from_file(args.organization_policy)
                result = route_organization_job(raw_job, organization, base_policy=routing_policy(args.policy))
            else:
                result = route_job(ModelJob.from_mapping(raw_job), policy=routing_policy(args.policy))
            _write(result, args.output)
            return 0
        if args.command == "prepare-handoff":
            organization = OrganizationPolicy.from_file(args.organization_policy) if args.organization_policy else None
            _write(prepare_handoff(_load(args.job), policy_name=args.policy, organization_policy=organization), args.output)
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
        if args.command == "operations-status":
            _write(SqliteExecutionLedger(args.ledger).operational_status(stale_after_seconds=args.stale_after), args.output)
            return 0
        if args.command == "recover-executions":
            recovered = SqliteExecutionLedger(args.ledger).recover_stale(stale_after_seconds=args.stale_after)
            _write({"contract_version": "execution-recovery-result.v1", "recovered_count": len(recovered)}, args.output)
            return 0
        if args.command == "backup-execution-ledger":
            _write(SqliteExecutionLedger(args.ledger).backup(args.destination), args.output)
            return 0
        if args.command == "prune-execution-artifacts":
            retention = ManagedArtifactRetention(SqliteExecutionLedger(args.ledger), args.managed_output_root)
            _write(retention.prune(older_than_seconds=args.older_than, dry_run=not args.apply), args.output)
            return 0
        if args.command == "qualify-release":
            report = qualify_local_release(_load(args.deployment_evidence) if args.deployment_evidence else None)
            _write(report, args.output)
            accepted = report["production_status"] == "accepted" if args.require_production else report["implementation_status"] == "passed"
            return 0 if accepted else 2
        if args.command == "run-acceptance-corpus":
            report = run_acceptance_corpus(_load(args.corpus))
            _write(report, args.output)
            accepted = report["production_status"] == "accepted" if args.require_practitioner else report["implementation_status"] == "passed"
            return 0 if accepted else 2
        if args.command == "run-guided-scoping-acceptance":
            report = run_guided_scoping_acceptance_corpus(_load(args.corpus))
            _write(report, args.output)
            accepted = report["production_status"] == "accepted" if args.require_practitioner else report["implementation_status"] == "passed"
            return 0 if accepted else 2
        issues = validate_execution_result(_load(args.result), handoff=_load(args.handoff))
        _write({"valid": not issues, "issues": list(issues)}, args.output)
        return 0 if not issues else 2
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        _write({"valid": False, "error": str(exc)})
        return 2
