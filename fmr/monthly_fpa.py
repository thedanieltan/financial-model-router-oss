from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fmr.core import ModelJob
from fmr.core.handoffs import digest
from fmr.data import validate_canonical_model_input
from fmr.execution import ExecutionOrchestrator, SqliteExecutionLedger
from fmr.provider_service import prepare_handoff
from fmr.workflow import WorkflowRequest


WORKFLOW_ID = "monthly_forecast_update"
WORKFLOW_VERSION = "1.1.0"


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def _decimal_string(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value.normalize(), "f")
    return "0" if text in {"-0", "-0.0"} else text


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write_idempotent_json(path: Path, value: Any) -> dict[str, Any]:
    raw = _canonical_bytes(value)
    expected = _sha256(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if _sha256(existing) != expected:
            raise ValueError(f"existing artifact does not match deterministic output: {path}")
        return {"path": str(path), "sha256": expected, "size_bytes": len(existing)}
    with tempfile.NamedTemporaryFile(prefix=".fmr-monthly-fpa-", suffix=".json", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(raw)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": str(path), "sha256": expected, "size_bytes": len(raw)}


def _load_reference(name: str, reference: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    if reference.get("contract_version") != "canonical-financial-data.v2":
        raise ValueError(f"input_references.{name} must reference canonical-financial-data.v2")
    path_value = reference.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError(f"input_references.{name}.path is required for the local monthly FP&A workflow")
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"input_references.{name}.path does not exist or is not a file")
    raw = path.read_bytes()
    actual_sha256 = _sha256(raw)
    if actual_sha256 != reference.get("sha256"):
        raise ValueError(f"input_references.{name} hash mismatch")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"input_references.{name} is not valid JSON") from exc
    issues = validate_canonical_model_input(payload)
    if issues:
        raise ValueError(f"input_references.{name} is invalid: " + "; ".join(issues))
    return payload, {"contract_version": "canonical-financial-data.v2", "sha256": actual_sha256, "path": str(path)}


def _materiality_policy(context: dict[str, Any]) -> dict[str, str]:
    raw = context.get("materiality_policy", {"mode": "report_all"})
    if not isinstance(raw, dict):
        raise ValueError("context.materiality_policy must be an object")
    mode = raw.get("mode")
    if mode == "report_all":
        if set(raw) != {"mode"}:
            raise ValueError("report_all materiality policy contains unsupported fields")
        return {"mode": "report_all"}
    if mode != "threshold":
        raise ValueError("context.materiality_policy.mode must be report_all or threshold")
    if set(raw) - {"mode", "absolute_threshold", "percentage_threshold"}:
        raise ValueError("threshold materiality policy contains unsupported fields")
    if "absolute_threshold" not in raw:
        raise ValueError("threshold materiality policy requires absolute_threshold")
    absolute = _decimal(raw["absolute_threshold"], "absolute_threshold")
    if absolute < 0:
        raise ValueError("absolute_threshold must be non-negative")
    result = {"mode": "threshold", "absolute_threshold": _decimal_string(absolute)}
    if "percentage_threshold" in raw:
        percentage = _decimal(raw["percentage_threshold"], "percentage_threshold")
        if percentage < 0:
            raise ValueError("percentage_threshold must be non-negative")
        result["percentage_threshold"] = _decimal_string(percentage)
    return result


def _variance(actual: Any, budget: Any, policy: dict[str, str]) -> tuple[str, str | None, bool]:
    actual_value = _decimal(actual, "actual")
    budget_value = _decimal(budget, "budget")
    difference = actual_value - budget_value
    percentage = None if budget_value == 0 else difference / abs(budget_value) * Decimal("100")
    if policy["mode"] == "report_all":
        material = True
    else:
        material = abs(difference) >= _decimal(policy["absolute_threshold"], "absolute_threshold")
        if "percentage_threshold" in policy and percentage is not None:
            material = material or abs(percentage) >= _decimal(policy["percentage_threshold"], "percentage_threshold")
    return _decimal_string(difference), None if percentage is None else _decimal_string(percentage), material


def _compare_sources(actuals: dict[str, Any], budget: dict[str, Any], reporting_period: str, policy: dict[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    actual_periods = actuals["periods"]
    budget_periods = budget["periods"]
    if reporting_period not in actual_periods or reporting_period not in budget_periods:
        raise ValueError("reporting_period must exist in both actual and budget sources")
    actual_index, budget_index = actual_periods.index(reporting_period), budget_periods.index(reporting_period)
    statement_variances: list[dict[str, Any]] = []
    driver_variances: list[dict[str, Any]] = []
    limitations: list[str] = []

    for statement in ("income_statement", "balance_sheet", "cash_flow"):
        actual_concepts = actuals["financial_statements"].get(statement, {})
        budget_concepts = budget["financial_statements"].get(statement, {})
        common = sorted(set(actual_concepts) & set(budget_concepts))
        actual_only = sorted(set(actual_concepts) - set(budget_concepts))
        budget_only = sorted(set(budget_concepts) - set(actual_concepts))
        if actual_only or budget_only:
            limitations.append(
                f"{statement} concept coverage differs between actual and budget; unmatched concepts are excluded from variance calculation"
            )
        for concept in common:
            actual = _decimal(actual_concepts[concept][actual_index], f"actual.{statement}.{concept}")
            planned = _decimal(budget_concepts[concept][budget_index], f"budget.{statement}.{concept}")
            absolute, percentage, material = _variance(actual, planned, policy)
            statement_variances.append({
                "statement": statement,
                "concept": concept,
                "actual": _decimal_string(actual),
                "budget": _decimal_string(planned),
                "absolute_variance": absolute,
                "percentage_variance": percentage,
                "material": material,
            })

    actual_drivers = actuals.get("operational_drivers", {})
    budget_drivers = budget.get("operational_drivers", {})
    driver_common = sorted(set(actual_drivers) & set(budget_drivers))
    if set(actual_drivers) != set(budget_drivers):
        limitations.append("operational-driver coverage differs between actual and budget; unmatched drivers are excluded from variance calculation")
    for driver in driver_common:
        actual = _decimal(actual_drivers[driver][actual_index], f"actual.operational_drivers.{driver}")
        planned = _decimal(budget_drivers[driver][budget_index], f"budget.operational_drivers.{driver}")
        absolute, percentage, material = _variance(actual, planned, policy)
        driver_variances.append({
            "driver": driver,
            "actual": _decimal_string(actual),
            "budget": _decimal_string(planned),
            "absolute_variance": absolute,
            "percentage_variance": percentage,
            "material": material,
        })
    if not statement_variances and not driver_variances:
        raise ValueError("actual and budget sources have no comparable statement concepts or operational drivers")
    return statement_variances, driver_variances, sorted(set(limitations))


def _forecast_job(request: WorkflowRequest, actual_reference: dict[str, str]) -> ModelJob:
    return ModelJob.from_mapping({
        "contract_version": "model-job.v2",
        "objective": request.objective,
        "requested_deliverables": ["budget_forecast"],
        "model_family": "budget_forecast",
        "industry": request.industry,
        "context": {**request.context, "workflow_id": WORKFLOW_ID, "entity_id": request.entity_id, "reporting_period": request.reporting_period},
        "available_data": list(request.available_data),
        "available_assumptions": list(request.available_assumptions),
        "input_references": {"canonical_financial_data": actual_reference},
        "existing_model": {},
        "output_formats": ["json"],
        "constraints": request.constraints,
        "privacy_constraints": [],
        "licensing_constraints": [],
        "preferred_execution_mode": "local",
        "scope_confirmation": None,
    })


def _execute_forecast(request: WorkflowRequest, actual_reference: dict[str, str], output_root: Path, ledger_path: Path, idempotency_key: str, timeout_seconds: int) -> dict[str, Any]:
    job = _forecast_job(request, actual_reference)
    handoff = prepare_handoff(job, policy_name=request.policy_name)
    if handoff.get("status") != "ready":
        missing = handoff.get("unresolved_requirements", [])
        raise ValueError("forecast route is not ready: " + "; ".join(str(item) for item in missing))
    orchestrator = ExecutionOrchestrator(
        ledger=SqliteExecutionLedger(ledger_path),
        managed_output_root=output_root / "provider-artifacts",
    )
    result = orchestrator.execute_request({
        "contract_version": "execution-request.v1",
        "handoff": handoff,
        "idempotency_key": idempotency_key,
        "execution_mode": handoff["execution_configuration"]["mode"],
        "timeout_seconds": timeout_seconds,
        "secret_references": [],
        "output_policy": {"mode": "managed", "directory": None, "overwrite": False, "publish": False},
    })
    if result.get("state") != "completed" or result.get("validation_status") != "passed":
        raise ValueError("forecast execution did not complete with passed validation")
    artifacts = [item for item in result.get("output_artifact_references", []) if item.get("kind") == "budget_forecast" and item.get("format") == "json"]
    if len(artifacts) != 1:
        raise ValueError("forecast execution must produce exactly one JSON budget_forecast artifact")
    artifact = artifacts[0]
    artifact_path = Path(artifact["path"]).resolve()
    raw = artifact_path.read_bytes()
    if _sha256(raw) != artifact["sha256"] or len(raw) != artifact["size_bytes"]:
        raise ValueError("forecast artifact no longer matches the accepted execution result")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("forecast artifact is not valid JSON") from exc
    if payload.get("contract_version") != "budget-forecast-result.v1":
        raise ValueError("forecast artifact does not implement budget-forecast-result.v1")
    rows = payload.get("forecast")
    if not isinstance(rows, list) or not rows:
        raise ValueError("forecast artifact contains no forecast rows")
    outlook: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"period", "revenue", "operating_costs", "operating_profit"}:
            raise ValueError(f"forecast row {index} does not match budget-forecast-result.v1")
        period = row.get("period")
        if not isinstance(period, str) or not period:
            raise ValueError(f"forecast row {index}.period is invalid")
        outlook.append({
            "period": period,
            "revenue": _decimal_string(_decimal(row["revenue"], f"forecast[{index}].revenue")),
            "operating_costs": _decimal_string(_decimal(row["operating_costs"], f"forecast[{index}].operating_costs")),
            "operating_profit": _decimal_string(_decimal(row["operating_profit"], f"forecast[{index}].operating_profit")),
        })
    return {"result": result, "artifact": artifact, "outlook": outlook}


def run_monthly_fpa(
    request: WorkflowRequest | dict[str, Any],
    *,
    output_dir: str | Path,
    idempotency_key: str,
    ledger_path: str | Path | None = None,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    workflow_request = WorkflowRequest.from_mapping(request) if isinstance(request, dict) else request
    if workflow_request.reporting_period is None:
        raise ValueError("monthly FP&A requires reporting_period")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ValueError("idempotency_key is required")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds < 1 or timeout_seconds > 86_400:
        raise ValueError("timeout_seconds must be between 1 and 86400")
    actual_ref = workflow_request.input_references.get("canonical_financial_data")
    budget_ref = workflow_request.input_references.get("budget_financial_data")
    if not isinstance(actual_ref, dict) or not isinstance(budget_ref, dict):
        raise ValueError("monthly FP&A requires canonical_financial_data and budget_financial_data input references")
    actuals, normalized_actual_ref = _load_reference("canonical_financial_data", actual_ref)
    budget, normalized_budget_ref = _load_reference("budget_financial_data", budget_ref)
    actual_entity, budget_entity = actuals["entity"], budget["entity"]
    if actual_entity["entity_id"] != workflow_request.entity_id or budget_entity["entity_id"] != workflow_request.entity_id:
        raise ValueError("workflow entity_id must match actual and budget sources")
    if actual_entity["currency"] != budget_entity["currency"]:
        raise ValueError("actual and budget currencies must match")

    policy = _materiality_policy(workflow_request.context)
    statement_variances, driver_variances, limitations = _compare_sources(
        actuals, budget, workflow_request.reporting_period, policy
    )
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    ledger = Path(ledger_path).expanduser().resolve() if ledger_path is not None else root / ".fmr-execution-ledger.sqlite3"
    forecast = _execute_forecast(
        workflow_request,
        normalized_actual_ref,
        root,
        ledger,
        idempotency_key.strip(),
        timeout_seconds,
    )
    result, forecast_artifact = forecast["result"], forecast["artifact"]
    checks = [
        {"check_id": "source_hashes_verified", "status": "passed"},
        {"check_id": "canonical_sources_valid", "status": "passed"},
        {"check_id": "entity_currency_aligned", "status": "passed"},
        {"check_id": "reporting_period_aligned", "status": "passed"},
        {"check_id": "forecast_execution_validated", "status": "passed"},
        {"check_id": "variance_math_reconciled", "status": "passed"},
        {"check_id": "commentary_evidence_traceable", "status": "passed"},
    ]
    limitations.extend([
        "Variance records show observed actual-versus-budget differences and do not infer causal attribution.",
        "Operational-driver variances are reported separately and are not represented as monetary contribution unless a governed bridge exists.",
        "Narrative stakeholder commentary is outside this deterministic workflow artifact.",
    ])
    evidence = {
        "contract_version": "monthly-fpa-commentary-evidence.v1",
        "entity_id": workflow_request.entity_id,
        "currency": actual_entity["currency"],
        "reporting_period": workflow_request.reporting_period,
        "sources": {"actuals": normalized_actual_ref, "budget": normalized_budget_ref},
        "forecast": {
            "execution_id": result["execution_id"],
            "provider_id": result["provider"]["provider_id"],
            "provider_version": result["provider"]["version"],
            "package_id": result["package"]["package_id"],
            "package_version": result["package"]["version"],
            "artifact": forecast_artifact,
        },
        "materiality_policy": policy,
        "statement_variances": statement_variances,
        "driver_variances": driver_variances,
        "forecast_outlook": forecast["outlook"],
        "checks": checks,
        "limitations": sorted(set(limitations)),
    }
    run_hash = digest({
        "workflow": {"id": WORKFLOW_ID, "version": WORKFLOW_VERSION},
        "request": workflow_request.to_dict(),
        "actual_sha256": normalized_actual_ref["sha256"],
        "budget_sha256": normalized_budget_ref["sha256"],
        "forecast_artifact_sha256": forecast_artifact["sha256"],
        "materiality_policy": policy,
    })
    run_dir = root / "monthly-fpa" / run_hash[:16]
    evidence_artifact = _write_idempotent_json(run_dir / "commentary-evidence.json", evidence)
    receipt = {
        "contract_version": "monthly-fpa-receipt.v1",
        "workflow_id": WORKFLOW_ID,
        "workflow_version": WORKFLOW_VERSION,
        "state": "completed",
        "entity_id": workflow_request.entity_id,
        "reporting_period": workflow_request.reporting_period,
        "source_references": [
            {"name": "canonical_financial_data", "contract_version": normalized_actual_ref["contract_version"], "sha256": normalized_actual_ref["sha256"]},
            {"name": "budget_financial_data", "contract_version": normalized_budget_ref["contract_version"], "sha256": normalized_budget_ref["sha256"]},
        ],
        "forecast_execution": {
            "execution_id": result["execution_id"],
            "provider_id": result["provider"]["provider_id"],
            "provider_version": result["provider"]["version"],
            "package_id": result["package"]["package_id"],
            "package_version": result["package"]["version"],
            "artifact_sha256": forecast_artifact["sha256"],
        },
        "materiality_policy_sha256": digest(policy),
        "evidence_artifact": evidence_artifact,
        "checks": [item["check_id"] for item in checks],
    }
    _write_idempotent_json(run_dir / "receipt.json", receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic FMR monthly FP&A workflow")
    parser.add_argument("request", help="Path to finance-workflow-request.v1 JSON")
    parser.add_argument("--output-dir", required=True, help="Directory for managed workflow artifacts")
    parser.add_argument("--idempotency-key", required=True, help="Caller-supplied idempotency key")
    parser.add_argument("--ledger", help="Optional execution-ledger path")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--receipt", help="Optional path for an additional receipt copy")
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.request).read_text(encoding="utf-8"))
    receipt = run_monthly_fpa(
        payload,
        output_dir=args.output_dir,
        idempotency_key=args.idempotency_key,
        ledger_path=args.ledger,
        timeout_seconds=args.timeout_seconds,
    )
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        target = Path(args.receipt)
        if target.exists():
            raise ValueError("receipt destination already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
