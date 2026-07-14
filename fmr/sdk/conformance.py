from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fmr.core.families import FAMILY_BY_ID
from fmr.core.receipts import validate_execution_result, validate_provider_handoff, validate_route_decision
from fmr.execution import ExecutionOrchestrator, SqliteExecutionLedger
from fmr.provider_plugins import PluginCatalog
from fmr.provider_service import prepare_handoff
from fmr.registry import ProviderManifest, ProviderRegistry


def run_manifest_conformance(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    try:
        manifest = ProviderManifest.from_mapping(payload)
        checks.append({"check": "manifest_contract", "status": "passed", "details": {}})
    except ValueError as exc:
        return _result(payload.get("provider_id"), [{"check": "manifest_contract", "status": "failed", "details": {"reason": str(exc)}}], "manifest")
    unknown_families = sorted({item.model_family for item in manifest.packages if item.model_family not in FAMILY_BY_ID})
    checks.append({"check": "registered_model_families", "status": "passed" if not unknown_families else "failed", "details": {"unknown_families": unknown_families}})
    plugins = PluginCatalog.installed()
    missing_adapters = sorted({item.adapter_entry_point for item in manifest.packages if item.adapter_entry_point not in plugins.adapter_loaders})
    missing_executors = [] if manifest.executor_entry_point in plugins.executor_loaders else [manifest.executor_entry_point]
    checks.append({"check": "installed_adapter_entry_points", "status": "passed" if not missing_adapters else "failed", "details": {"missing": missing_adapters}})
    checks.append({"check": "installed_executor_entry_point", "status": "passed" if not missing_executors else "failed", "details": {"missing": missing_executors}})
    checks.append({"check": "version_pins", "status": "passed", "details": {"provider_version": manifest.version, "package_versions": sorted(f"{item.package_id}@{item.version}" for item in manifest.packages)}})
    return _result(manifest.provider_id, checks, "manifest")


def run_provider_conformance(payload: dict[str, Any], fixture_job: dict[str, Any]) -> dict[str, Any]:
    manifest_result = run_manifest_conformance(payload)
    checks = list(manifest_result["checks"])
    if manifest_result["status"] != "passed":
        return _result(payload.get("provider_id"), checks, "executable")
    manifest = ProviderManifest.from_mapping(payload)
    plugins = PluginCatalog.installed()
    registry = ProviderRegistry(
        [manifest], runtime_availability={manifest.provider_id: True},
        installed_adapter_entry_points=plugins.adapter_loaders,
        installed_executor_entry_points=plugins.executor_loaders,
    )
    try:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = prepare_handoff(fixture_job, registry=registry, plugins=plugins)
            route_issues = validate_route_decision(handoff["route_decision"], job=handoff["job"], registry=registry)
            handoff_issues = validate_provider_handoff(handoff, registry=registry)
            checks.append({"check": "route_and_handoff", "status": "passed" if not route_issues and not handoff_issues else "failed", "details": {"issues": [*route_issues, *handoff_issues]}})
            orchestrator = ExecutionOrchestrator(registry=registry, ledger=SqliteExecutionLedger(root / "ledger.sqlite3"), managed_output_root=root / "outputs")
            result = orchestrator.execute_request({
                "contract_version": "execution-request.v1", "handoff": handoff, "idempotency_key": "conformance",
                "execution_mode": manifest.execution_mode, "timeout_seconds": 30, "secret_references": list(manifest.secret_requirements),
                "output_policy": {"mode": "managed", "overwrite": False, "publish": False},
            })
            result_issues = validate_execution_result(result, handoff=handoff, registry=registry)
            checks.append({"check": "execution_and_artifacts", "status": "passed" if not result_issues else "failed", "details": {"issues": list(result_issues)}})
            second = orchestrator.execute_request({
                "contract_version": "execution-request.v1", "handoff": handoff, "idempotency_key": "conformance",
                "execution_mode": manifest.execution_mode, "timeout_seconds": 30, "secret_references": list(manifest.secret_requirements),
                "output_policy": {"mode": "managed", "overwrite": False, "publish": False},
            })
            checks.append({"check": "durable_idempotency", "status": "passed" if second == result else "failed", "details": {}})
    except (OSError, RuntimeError, ValueError) as exc:
        checks.append({"check": "executable_lifecycle", "status": "failed", "details": {"reason": str(exc)}})
    return _result(manifest.provider_id, checks, "executable")


def _result(provider_id: Any, checks: list[dict[str, Any]], level: str) -> dict[str, Any]:
    return {
        "contract_version": "provider-conformance-result.v1", "conformance_level": level,
        "status": "passed" if checks and all(item["status"] == "passed" for item in checks) else "failed",
        "provider_id": provider_id, "checks": checks,
    }
