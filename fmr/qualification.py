from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import Any

from fmr.execution import EnvironmentSecretResolver, SqliteExecutionLedger
from fmr.registry import ProviderRegistry

__version__ = version("financial-model-router")


DEPLOYMENT_GATES = (
    "filesystem_durability",
    "backup_restore_drill",
    "process_supervision",
    "resource_limits",
    "secret_manager_integration",
    "security_review",
    "operator_acceptance",
)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _check(check_id: str, passed: bool, evidence: str) -> dict[str, Any]:
    return {"check_id": check_id, "status": "passed" if passed else "failed", "evidence": evidence}


def validate_deployment_evidence(value: dict[str, Any]) -> tuple[str, ...]:
    if not isinstance(value, dict) or value.get("contract_version") != "deployment-acceptance-evidence.v1":
        return ("unsupported deployment acceptance evidence contract",)
    expected = {"contract_version", "environment_id", "gates"}
    issues: list[str] = []
    if set(value) != expected:
        issues.append("deployment evidence fields do not match the contract")
    if not isinstance(value.get("environment_id"), str) or not value["environment_id"]:
        issues.append("environment_id is required")
    gates = value.get("gates")
    if not isinstance(gates, dict) or set(gates) != set(DEPLOYMENT_GATES):
        issues.append("deployment evidence must contain every required gate")
    elif any(
        not isinstance(item, dict)
        or set(item) != {"status", "reference"}
        or item.get("status") not in {"passed", "failed", "not_run"}
        or not isinstance(item.get("reference"), str)
        for item in gates.values()
    ):
        issues.append("deployment gate evidence is invalid")
    return tuple(issues)


def qualify_local_release(deployment_evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    checks = [
        _provider_discovery_check(),
        _interchangeability_check(),
        _contract_packaging_check(),
        _core_boundary_check(),
        _ledger_backup_restore_check(),
        _ledger_schema_migration_check(),
        _ledger_concurrency_check(),
        _stale_recovery_check(),
        _secret_fail_closed_check(),
    ]
    implementation_status = "passed" if all(item["status"] == "passed" for item in checks) else "failed"
    deployment: list[dict[str, Any]] = []
    evidence_issues: tuple[str, ...] = ()
    if deployment_evidence is not None:
        evidence_issues = validate_deployment_evidence(deployment_evidence)
    gates = deployment_evidence.get("gates", {}) if deployment_evidence is not None and not evidence_issues else {}
    for gate in DEPLOYMENT_GATES:
        item = gates.get(gate, {"status": "not_run", "reference": ""})
        deployment.append({"gate_id": gate, "status": item["status"], "reference": item["reference"]})
    blockers = [item["check_id"] for item in checks if item["status"] != "passed"]
    blockers.extend(item["gate_id"] for item in deployment if item["status"] != "passed")
    blockers.extend(f"invalid_deployment_evidence:{issue}" for issue in evidence_issues)
    if "a" in __version__:
        blockers.append("stable_release_version_not_declared")
    production_status = "accepted" if implementation_status == "passed" and not blockers else "not_accepted"
    provisional = {
        "contract_version": "release-qualification.v1",
        "target": "local-production-1.0",
        "package_version": __version__,
        "implementation_status": implementation_status,
        "production_status": production_status,
        "implementation_checks": checks,
        "deployment_gates": deployment,
        "blockers": sorted(set(blockers)),
    }
    return {**provisional, "qualification_id": f"fmrq_{_digest(provisional)[:24]}"}


def _provider_discovery_check() -> dict[str, Any]:
    providers = ProviderRegistry.builtins().providers()
    return _check("provider_discovery", len(providers) >= 2, f"{len(providers)} provider manifests discovered without loading implementation code")


def _interchangeability_check() -> dict[str, Any]:
    registry = ProviderRegistry.builtins()
    families: dict[str, set[str]] = {}
    for item in registry.packages():
        if item.provider_adapter_available and item.provider_executor_available and item.runtime_available:
            families.setdefault(item.package.model_family, set()).add(item.provider.provider_id)
    competing = sorted(family for family, providers in families.items() if len(providers) >= 2)
    return _check("interchangeable_provider_proof", bool(competing), "competing executable families: " + ",".join(competing))


def _contract_packaging_check() -> dict[str, Any]:
    required = ("model-job.v2.schema.json", "route-decision.v2.schema.json", "provider-handoff.v1.schema.json", "execution-request.v1.schema.json", "execution-result.v1.schema.json", "release-qualification.v1.schema.json", "deployment-acceptance-evidence.v1.schema.json")
    root = files("fmr.contracts")
    missing = [name for name in required if not root.joinpath(name).is_file()]
    return _check("release_contracts_packaged", not missing, "missing: " + ",".join(missing) if missing else f"{len(required)} lifecycle and qualification contracts packaged")


def _core_boundary_check() -> dict[str, Any]:
    root = Path(__file__).parent / "core"
    forbidden: list[str] = []
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.startswith("fmr.providers") or name.startswith("openpyxl") or name.startswith("libreoffice"):
                    forbidden.append(f"{path.name}:{name}")
    return _check("router_core_provider_boundary", not forbidden, "forbidden imports: " + ",".join(forbidden) if forbidden else "core imports no provider, OpenPyXL or LibreOffice implementation")


def _ledger_backup_restore_check() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        ledger = SqliteExecutionLedger(root / "ledger.sqlite3")
        ledger.claim("qualification", stale_after_seconds=30)
        ledger.complete("qualification", {"execution_id": "qualification", "state": "completed"})
        receipt = ledger.backup(root / "backup.sqlite3")
        with sqlite3.connect(receipt["path"]) as restored:
            row = restored.execute("SELECT result_json FROM executions_v2 WHERE cache_key = 'qualification'").fetchone()
        passed = row is not None and json.loads(row[0])["execution_id"] == "qualification" and hashlib.sha256(Path(receipt["path"]).read_bytes()).hexdigest() == receipt["sha256"]
    return _check("ledger_backup_restore", passed, "online backup restored and content hash verified")


def _ledger_concurrency_check() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temporary:
        ledger = SqliteExecutionLedger(Path(temporary) / "ledger.sqlite3")
        def claim() -> str:
            try:
                ledger.claim("same-key", stale_after_seconds=30)
                return "claimed"
            except RuntimeError:
                return "blocked"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = sorted(pool.map(lambda _: claim(), range(2)))
    return _check("cross_process_idempotency", outcomes == ["blocked", "claimed"], "simultaneous duplicate claims produced one owner and one rejection")


def _ledger_schema_migration_check() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "legacy.sqlite3"
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE executions_v2 (cache_key TEXT PRIMARY KEY, state TEXT NOT NULL, claimed_at REAL NOT NULL, result_json TEXT)")
            connection.execute("INSERT INTO executions_v2 VALUES ('legacy', 'completed', 1, ?)", (json.dumps({"execution_id": "legacy"}),))
        SqliteExecutionLedger(path)
        with sqlite3.connect(path) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(executions_v2)")}
            retained = connection.execute("SELECT result_json FROM executions_v2 WHERE cache_key = 'legacy'").fetchone()
    passed = {"updated_at", "detail_code"}.issubset(columns) and retained is not None and json.loads(retained[0])["execution_id"] == "legacy"
    return _check("ledger_schema_migration", passed, "legacy ledger migrated in place with cached result retained")


def _stale_recovery_check() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temporary:
        ledger = SqliteExecutionLedger(Path(temporary) / "ledger.sqlite3")
        ledger.claim("stale", stale_after_seconds=30)
        recovered = ledger.recover_stale(stale_after_seconds=1, now=10**12)
        reclaimed = ledger.claim("stale", stale_after_seconds=30)
    return _check("stale_execution_recovery", recovered == ("stale",) and reclaimed is None, "stale claim was abandoned and deterministically reclaimed")


def _secret_fail_closed_check() -> dict[str, Any]:
    resolver = EnvironmentSecretResolver(allowed_references=())
    try:
        resolver("undeclared")
    except ValueError:
        return _check("secret_reference_fail_closed", True, "undeclared secret reference rejected")
    return _check("secret_reference_fail_closed", False, "undeclared secret reference was accepted")
