from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from fmr.core import ModelJob, route_job, routing_policy
from fmr.execution import ExecutionOrchestrator, SqliteExecutionLedger
from fmr.provider_service import prepare_handoff


_ALLOWED_ROLES = {
    "finance_manager",
    "fp_and_a",
    "project_finance",
    "venture_capital",
    "growth_equity",
    "private_equity",
    "portfolio_operations",
}


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _strings(value: Any, field: str, *, required: bool = False) -> tuple[str, ...]:
    if value is None:
        value = []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field} must be an array of non-empty strings")
    cleaned = tuple(sorted(item.strip() for item in value))
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{field} must not contain duplicates")
    if required and not cleaned:
        raise ValueError(f"{field} must contain at least one item")
    return cleaned


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return dict(value)


def _validate_reference(name: str, reference: Any) -> dict[str, Any]:
    if not isinstance(reference, dict):
        raise ValueError(f"input_references.{name} must be an object")
    allowed = {"contract_version", "sha256", "path", "uri"}
    if set(reference) - allowed:
        raise ValueError(f"input_references.{name} contains unsupported fields")
    contract = _non_empty_string(reference.get("contract_version"), f"input_references.{name}.contract_version")
    sha256 = reference.get("sha256")
    if not isinstance(sha256, str) or len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
        raise ValueError(f"input_references.{name}.sha256 is invalid")
    locations = [key for key in ("path", "uri") if isinstance(reference.get(key), str) and reference[key].strip()]
    if not locations:
        raise ValueError(f"input_references.{name} requires path or uri")
    return {"contract_version": contract, "sha256": sha256, **{key: reference[key].strip() for key in locations}}


@dataclass(frozen=True)
class WorkflowRequest:
    objective: str
    role: str
    entity_id: str
    reporting_period: str | None
    requested_outputs: tuple[str, ...]
    available_data: tuple[str, ...]
    available_assumptions: tuple[str, ...]
    input_references: dict[str, Any]
    industry: str | None
    output_formats: tuple[str, ...]
    policy_name: str
    constraints: dict[str, Any]
    context: dict[str, Any]
    contract_version: str = "finance-workflow-request.v1"

    @classmethod
    def from_mapping(cls, value: Any) -> "WorkflowRequest":
        if not isinstance(value, dict) or value.get("contract_version") != "finance-workflow-request.v1":
            raise ValueError("finance-workflow-request.v1 is required")
        allowed = {
            "contract_version",
            "objective",
            "role",
            "entity_id",
            "reporting_period",
            "requested_outputs",
            "available_data",
            "available_assumptions",
            "input_references",
            "industry",
            "output_formats",
            "policy_name",
            "constraints",
            "context",
        }
        if set(value) - allowed:
            raise ValueError("workflow request contains unsupported fields")
        role = _non_empty_string(value.get("role"), "role")
        if role not in _ALLOWED_ROLES:
            raise ValueError("role is not supported")
        reporting_period = value.get("reporting_period")
        if reporting_period is not None:
            reporting_period = _non_empty_string(reporting_period, "reporting_period")
        industry = value.get("industry")
        if industry is not None:
            industry = _non_empty_string(industry, "industry")
        references = {
            name: _validate_reference(name, reference)
            for name, reference in sorted(_mapping(value.get("input_references"), "input_references").items())
        }
        output_formats = _strings(value.get("output_formats", ["json"]), "output_formats", required=True)
        policy_name = _non_empty_string(value.get("policy_name", "default"), "policy_name")
        constraints = _mapping(value.get("constraints"), "constraints")
        allowed_constraints = {
            "local_only",
            "open_source_only",
            "network_allowed",
            "allowed_providers",
            "prohibited_providers",
            "pinned_provider_versions",
        }
        if set(constraints) - allowed_constraints:
            raise ValueError("constraints contains unsupported fields")
        return cls(
            objective=_non_empty_string(value.get("objective"), "objective"),
            role=role,
            entity_id=_non_empty_string(value.get("entity_id"), "entity_id"),
            reporting_period=reporting_period,
            requested_outputs=_strings(value.get("requested_outputs"), "requested_outputs", required=True),
            available_data=_strings(value.get("available_data"), "available_data"),
            available_assumptions=_strings(value.get("available_assumptions"), "available_assumptions"),
            input_references=references,
            industry=industry,
            output_formats=output_formats,
            policy_name=policy_name,
            constraints=constraints,
            context=_mapping(value.get("context"), "context"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "objective": self.objective,
            "role": self.role,
            "entity_id": self.entity_id,
            "reporting_period": self.reporting_period,
            "requested_outputs": list(self.requested_outputs),
            "available_data": list(self.available_data),
            "available_assumptions": list(self.available_assumptions),
            "input_references": self.input_references,
            "industry": self.industry,
            "output_formats": list(self.output_formats),
            "policy_name": self.policy_name,
            "constraints": self.constraints,
            "context": self.context,
        }


BUILTIN_WORKFLOW_BLUEPRINTS: tuple[dict[str, Any], ...] = (
    {
        "blueprint_id": "monthly_forecast_update",
        "version": "1.0.0",
        "roles": ["finance_manager", "fp_and_a", "portfolio_operations"],
        "objective_terms": ["forecast update", "rolling forecast", "full year forecast", "actuals", "management forecast"],
        "output_terms": ["rolling_forecast", "variance_analysis", "cash_outlook", "management_pack"],
        "steps": [
            {"step_id": "validate_sources", "kind": "internal", "capability": "source_validation", "depends_on": [], "consumes": ["input_references"], "produces": ["validated_sources"], "mandatory": True},
            {"step_id": "refresh_forecast", "kind": "model", "capability": "budget_forecast", "model_family": "budget_forecast", "requested_deliverables": ["budget_forecast"], "depends_on": ["validate_sources"], "consumes": ["income_statement_history", "operating_cost_drivers", "revenue_drivers", "forecast_horizon", "revenue_growth_rate", "operating_cost_growth_rate", "scenario", "scenario_adjustments"], "produces": ["rolling_forecast"], "mandatory": True},
            {"step_id": "refresh_statements", "kind": "model", "capability": "three_statement", "model_family": "three_statement", "requested_deliverables": ["three_statement_forecast"], "depends_on": ["validate_sources"], "consumes": ["balance_sheet_history", "capital_expenditure", "cash_flow_history", "debt_schedule", "income_statement_history", "working_capital", "capital_expenditure_rate", "depreciation_rate", "forecast_horizon", "operating_margin_rate", "revenue_growth_rate", "tax_rate", "working_capital_rate"], "produces": ["cash_outlook", "three_statement_forecast"], "mandatory": False},
            {"step_id": "review_forecast", "kind": "human_gate", "capability": "review", "depends_on": ["refresh_forecast"], "consumes": ["rolling_forecast"], "produces": ["approved_forecast"], "mandatory": True},
            {"step_id": "assemble_outputs", "kind": "assembly", "capability": "artifact_assembly", "depends_on": ["review_forecast"], "consumes": ["approved_forecast"], "produces": ["management_pack"], "mandatory": True},
        ],
    },
    {
        "blueprint_id": "scenario_analysis",
        "version": "1.0.0",
        "roles": ["finance_manager", "fp_and_a", "project_finance", "venture_capital", "growth_equity", "private_equity", "portfolio_operations"],
        "objective_terms": ["scenario", "downside", "upside", "sensitivity", "stress case"],
        "output_terms": ["scenario_comparison", "downside_case", "upside_case"],
        "steps": [
            {"step_id": "validate_sources", "kind": "internal", "capability": "source_validation", "depends_on": [], "consumes": ["input_references"], "produces": ["validated_sources"], "mandatory": True},
            {"step_id": "run_scenario", "kind": "model", "capability": "budget_forecast", "model_family": "budget_forecast", "requested_deliverables": ["budget_forecast"], "depends_on": ["validate_sources"], "consumes": ["income_statement_history", "operating_cost_drivers", "revenue_drivers", "forecast_horizon", "revenue_growth_rate", "operating_cost_growth_rate", "scenario", "scenario_adjustments"], "produces": ["scenario_comparison"], "mandatory": True},
            {"step_id": "review_scenario", "kind": "human_gate", "capability": "review", "depends_on": ["run_scenario"], "consumes": ["scenario_comparison"], "produces": ["approved_scenario"], "mandatory": True},
        ],
    },
    {
        "blueprint_id": "operating_company_valuation",
        "version": "1.0.0",
        "roles": ["venture_capital", "growth_equity", "private_equity", "portfolio_operations", "finance_manager"],
        "objective_terms": ["valuation", "dcf", "enterprise value", "equity value", "value company"],
        "output_terms": ["enterprise_value", "equity_value", "operating_company_dcf"],
        "steps": [
            {"step_id": "validate_sources", "kind": "internal", "capability": "source_validation", "depends_on": [], "consumes": ["input_references"], "produces": ["validated_sources"], "mandatory": True},
            {"step_id": "calculate_dcf", "kind": "model", "capability": "operating_company_dcf", "model_family": "operating_company_dcf", "requested_deliverables": ["enterprise_value", "equity_value", "operating_forecast"], "depends_on": ["validate_sources"], "consumes": ["capital_expenditure", "cash_flow_history", "income_statement_history", "net_debt", "revenue_drivers", "working_capital", "capital_expenditure_rate", "depreciation_rate", "discount_rate", "forecast_horizon", "operating_margin_rate", "revenue_growth_rate", "tax_rate", "terminal_growth_rate", "terminal_value_assumption", "working_capital_rate"], "produces": ["enterprise_value", "equity_value", "operating_company_dcf"], "mandatory": True},
            {"step_id": "review_valuation", "kind": "human_gate", "capability": "investment_review", "depends_on": ["calculate_dcf"], "consumes": ["operating_company_dcf"], "produces": ["approved_valuation"], "mandatory": True},
        ],
    },
    {
        "blueprint_id": "debt_capacity_refresh",
        "version": "1.0.0",
        "roles": ["finance_manager", "project_finance", "private_equity", "portfolio_operations"],
        "objective_terms": ["debt capacity", "refinancing", "covenant", "leverage", "debt headroom"],
        "output_terms": ["debt_capacity", "refinancing_analysis", "covenant_headroom"],
        "steps": [
            {"step_id": "validate_sources", "kind": "internal", "capability": "source_validation", "depends_on": [], "consumes": ["input_references"], "produces": ["validated_sources"], "mandatory": True},
            {"step_id": "calculate_debt_capacity", "kind": "model", "capability": "debt_capacity_refinancing", "model_family": "debt_capacity_refinancing", "requested_deliverables": ["debt_capacity", "refinancing_analysis"], "depends_on": ["validate_sources"], "consumes": ["cash_flow_history", "debt_schedule", "income_statement_history", "liquidity_position", "annual_repayment", "covenant_thresholds", "ebitda_growth_rate", "forecast_horizon", "interest_rate_assumption", "maximum_leverage_ratio", "minimum_debt_service_coverage", "opening_debt", "repayment_terms"], "produces": ["debt_capacity", "refinancing_analysis", "covenant_headroom"], "mandatory": True},
            {"step_id": "review_debt", "kind": "human_gate", "capability": "treasury_review", "depends_on": ["calculate_debt_capacity"], "consumes": ["debt_capacity", "covenant_headroom"], "produces": ["approved_debt_case"], "mandatory": True},
        ],
    },
    {
        "blueprint_id": "project_finance_debt_sizing",
        "version": "1.0.0",
        "roles": ["project_finance"],
        "objective_terms": ["debt sculpting", "dscr", "llcr", "plcr", "project finance", "construction delay"],
        "output_terms": ["debt_sizing", "debt_sculpting", "dscr", "llcr", "plcr"],
        "steps": [
            {"step_id": "validate_project_sources", "kind": "internal", "capability": "source_validation", "depends_on": [], "consumes": ["input_references"], "produces": ["validated_sources"], "mandatory": True},
            {"step_id": "size_project_debt", "kind": "model", "capability": "project_finance", "model_family": "project_finance", "requested_deliverables": ["debt_sizing", "debt_sculpting", "dscr", "llcr", "plcr"], "depends_on": ["validate_project_sources"], "consumes": ["project_cash_flow", "construction_schedule", "debt_terms", "coverage_targets"], "produces": ["project_finance_model"], "mandatory": True},
        ],
    },
    {
        "blueprint_id": "leveraged_buyout_screening",
        "version": "1.0.0",
        "roles": ["private_equity"],
        "objective_terms": ["lbo", "leveraged buyout", "acquisition returns", "sponsor returns"],
        "output_terms": ["lbo_model", "moic", "irr", "sources_and_uses"],
        "steps": [
            {"step_id": "validate_sources", "kind": "internal", "capability": "source_validation", "depends_on": [], "consumes": ["input_references"], "produces": ["validated_sources"], "mandatory": True},
            {"step_id": "build_lbo", "kind": "model", "capability": "leveraged_buyout", "model_family": "leveraged_buyout", "requested_deliverables": ["lbo_model", "moic", "irr", "sources_and_uses"], "depends_on": ["validate_sources"], "consumes": ["historical_financials", "entry_assumptions", "debt_terms", "exit_assumptions"], "produces": ["lbo_model"], "mandatory": True},
        ],
    },
    {
        "blueprint_id": "venture_follow_on_analysis",
        "version": "1.0.0",
        "roles": ["venture_capital", "growth_equity"],
        "objective_terms": ["follow on", "financing round", "dilution", "pro rata", "cap table"],
        "output_terms": ["dilution", "ownership", "follow_on_returns", "cap_table"],
        "steps": [
            {"step_id": "validate_sources", "kind": "internal", "capability": "source_validation", "depends_on": [], "consumes": ["input_references"], "produces": ["validated_sources"], "mandatory": True},
            {"step_id": "model_financing_round", "kind": "model", "capability": "cap_table_dilution", "model_family": "cap_table_dilution", "requested_deliverables": ["dilution", "ownership", "follow_on_returns", "cap_table"], "depends_on": ["validate_sources"], "consumes": ["cap_table", "round_terms", "exit_scenarios"], "produces": ["follow_on_analysis"], "mandatory": True},
        ],
    },
)


def _validate_blueprint(blueprint: dict[str, Any]) -> None:
    required = {"blueprint_id", "version", "roles", "objective_terms", "output_terms", "steps"}
    if set(blueprint) != required:
        raise ValueError("workflow blueprint fields do not match the contract")
    _non_empty_string(blueprint["blueprint_id"], "blueprint_id")
    _non_empty_string(blueprint["version"], "version")
    roles = _strings(blueprint["roles"], "roles", required=True)
    if not set(roles).issubset(_ALLOWED_ROLES):
        raise ValueError("workflow blueprint declares an unsupported role")
    _strings(blueprint["objective_terms"], "objective_terms", required=True)
    _strings(blueprint["output_terms"], "output_terms", required=True)
    if not isinstance(blueprint["steps"], list) or not blueprint["steps"]:
        raise ValueError("workflow blueprint must contain steps")
    ids: set[str] = set()
    dependencies: dict[str, tuple[str, ...]] = {}
    for step in blueprint["steps"]:
        if not isinstance(step, dict):
            raise ValueError("workflow blueprint steps must be objects")
        allowed = {"step_id", "kind", "capability", "model_family", "requested_deliverables", "depends_on", "consumes", "produces", "mandatory"}
        if set(step) - allowed:
            raise ValueError("workflow blueprint step contains unsupported fields")
        step_id = _non_empty_string(step.get("step_id"), "step_id")
        if step_id in ids:
            raise ValueError("workflow blueprint step identifiers must be unique")
        ids.add(step_id)
        kind = step.get("kind")
        if kind not in {"internal", "model", "human_gate", "assembly"}:
            raise ValueError("workflow blueprint step kind is unsupported")
        _non_empty_string(step.get("capability"), "capability")
        dependencies[step_id] = _strings(step.get("depends_on"), "depends_on")
        _strings(step.get("consumes"), "consumes")
        _strings(step.get("produces"), "produces", required=True)
        if not isinstance(step.get("mandatory"), bool):
            raise ValueError("workflow blueprint step mandatory must be boolean")
        if kind == "model":
            _non_empty_string(step.get("model_family"), "model_family")
            _strings(step.get("requested_deliverables"), "requested_deliverables", required=True)
    for step_id, values in dependencies.items():
        if step_id in values:
            raise ValueError("workflow blueprint contains a self dependency")
        unknown = set(values) - ids
        if unknown:
            raise ValueError("workflow blueprint contains an unknown dependency")
    _topological_order(dependencies)


def builtin_workflow_blueprints() -> tuple[dict[str, Any], ...]:
    for blueprint in BUILTIN_WORKFLOW_BLUEPRINTS:
        _validate_blueprint(blueprint)
    return tuple(json.loads(json.dumps(item, sort_keys=True)) for item in BUILTIN_WORKFLOW_BLUEPRINTS)


def _topological_order(dependencies: dict[str, Iterable[str]]) -> tuple[str, ...]:
    remaining = {key: set(values) for key, values in dependencies.items()}
    order: list[str] = []
    while remaining:
        ready = sorted(key for key, values in remaining.items() if not values)
        if not ready:
            raise ValueError("workflow graph contains a cycle")
        for key in ready:
            order.append(key)
            remaining.pop(key)
        for values in remaining.values():
            values.difference_update(ready)
    return tuple(order)


def _normalize_text(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def _select_blueprint(request: WorkflowRequest, blueprints: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    objective = _normalize_text(request.objective)
    requested = set(request.requested_outputs)
    candidates: list[tuple[int, str, dict[str, Any], dict[str, Any]]] = []
    evidence: list[dict[str, Any]] = []
    for blueprint in blueprints:
        if request.role not in blueprint["roles"]:
            continue
        matched_terms = sorted(term for term in blueprint["objective_terms"] if _normalize_text(term) in objective)
        output_matches = sorted(requested.intersection(blueprint["output_terms"]))
        score = sum(len(term.split()) for term in matched_terms) * 10 + len(output_matches) * 3
        record = {
            "blueprint_id": blueprint["blueprint_id"],
            "version": blueprint["version"],
            "score": score,
            "matched_objective_terms": matched_terms,
            "matched_outputs": output_matches,
        }
        evidence.append(record)
        if score:
            candidates.append((score, blueprint["blueprint_id"], blueprint, record))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    if not candidates:
        raise ValueError("workflow objective does not match a supported practitioner workflow")
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        raise ValueError("workflow objective is ambiguous between supported practitioner workflows")
    return candidates[0][2], sorted(evidence, key=lambda item: (-item["score"], item["blueprint_id"]))


def _job_for_step(request: WorkflowRequest, workflow_id: str, step: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": "model-job.v2",
        "objective": f"{request.objective} — {step['capability']}",
        "requested_deliverables": list(step["requested_deliverables"]),
        "model_family": step["model_family"],
        "industry": request.industry,
        "context": {
            **request.context,
            "workflow_id": workflow_id,
            "workflow_step_id": step["step_id"],
            "entity_id": request.entity_id,
            "reporting_period": request.reporting_period,
            "practitioner_role": request.role,
        },
        "available_data": list(request.available_data),
        "available_assumptions": list(request.available_assumptions),
        "input_references": request.input_references,
        "existing_model": {},
        "output_formats": list(request.output_formats),
        "constraints": request.constraints,
        "privacy_constraints": [],
        "licensing_constraints": [],
        "preferred_execution_mode": "local" if request.constraints.get("local_only") else None,
        "scope_confirmation": None,
    }


def compile_workflow(request: WorkflowRequest | dict[str, Any], *, blueprints: tuple[dict[str, Any], ...] | None = None) -> dict[str, Any]:
    workflow_request = WorkflowRequest.from_mapping(request) if isinstance(request, dict) else request
    registry = blueprints or builtin_workflow_blueprints()
    for blueprint in registry:
        _validate_blueprint(blueprint)
    selected, selection_evidence = _select_blueprint(workflow_request, registry)
    request_payload = workflow_request.to_dict()
    request_sha256 = _digest(request_payload)
    workflow_seed = {
        "request_sha256": request_sha256,
        "blueprint_id": selected["blueprint_id"],
        "blueprint_version": selected["version"],
    }
    workflow_id = f"fmrwf_{_digest(workflow_seed)[:24]}"
    steps: list[dict[str, Any]] = []
    blockers: set[str] = set()
    dependencies = {step["step_id"]: tuple(step["depends_on"]) for step in selected["steps"]}
    order = _topological_order(dependencies)
    by_id = {step["step_id"]: step for step in selected["steps"]}
    for position, step_id in enumerate(order):
        blueprint_step = by_id[step_id]
        kind = blueprint_step["kind"]
        step_status = "ready"
        route = None
        model_job = None
        step_blockers: list[str] = []
        if kind == "internal" and blueprint_step["capability"] == "source_validation":
            if not workflow_request.input_references:
                step_status = "blocked"
                step_blockers.append("missing_input_reference")
        elif kind == "model":
            model_job = _job_for_step(workflow_request, workflow_id, blueprint_step)
            route = route_job(ModelJob.from_mapping(model_job), policy=routing_policy(workflow_request.policy_name))
            if route["status"] != "selected":
                step_status = "blocked"
                step_blockers.extend(route.get("missing_requirements", []))
                if route["status"] in {"unsupported_family", "ambiguous_family"}:
                    step_blockers.append(f"route_status:{route['status']}")
                if not step_blockers:
                    step_blockers.append("no_executable_provider")
        elif kind == "human_gate":
            step_status = "awaiting_approval"
        elif kind == "assembly":
            step_status = "waiting_on_dependencies"
        if blueprint_step["mandatory"]:
            blockers.update(step_blockers)
        step_provisional = {
            "step_id": step_id,
            "position": position,
            "kind": kind,
            "capability": blueprint_step["capability"],
            "mandatory": blueprint_step["mandatory"],
            "depends_on": list(blueprint_step["depends_on"]),
            "consumes": list(blueprint_step["consumes"]),
            "produces": list(blueprint_step["produces"]),
            "status": step_status,
            "blockers": sorted(set(step_blockers)),
            "model_job": model_job,
            "route_decision": route,
        }
        steps.append({**step_provisional, "step_sha256": _digest(step_provisional)})
    mandatory_blocked = any(step["mandatory"] and step["status"] == "blocked" for step in steps)
    plan_status = "blocked" if mandatory_blocked else "ready_with_approval_gates" if any(step["kind"] == "human_gate" for step in steps) else "ready"
    provisional = {
        "contract_version": "finance-workflow-plan.v1",
        "workflow_id": workflow_id,
        "request_sha256": request_sha256,
        "request": request_payload,
        "blueprint": {"blueprint_id": selected["blueprint_id"], "version": selected["version"]},
        "selection_evidence": selection_evidence,
        "status": plan_status,
        "steps": steps,
        "missing_requirements": sorted(blockers),
    }
    return {**provisional, "workflow_sha256": _digest(provisional)}


def validate_workflow_plan(value: Any) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(value, dict) or value.get("contract_version") != "finance-workflow-plan.v1":
        return ("finance-workflow-plan.v1 is required",)
    required = {"contract_version", "workflow_id", "workflow_sha256", "request_sha256", "request", "blueprint", "selection_evidence", "status", "steps", "missing_requirements"}
    if set(value) != required:
        issues.append("workflow plan fields do not match the contract")
        return tuple(issues)
    try:
        request = WorkflowRequest.from_mapping(value["request"])
    except ValueError as exc:
        issues.append(str(exc))
        return tuple(issues)
    if value["request_sha256"] != _digest(request.to_dict()):
        issues.append("workflow request hash does not match")
    if not isinstance(value.get("steps"), list) or not value["steps"]:
        issues.append("workflow plan must contain steps")
        return tuple(issues)
    ids: set[str] = set()
    dependencies: dict[str, tuple[str, ...]] = {}
    for step in value["steps"]:
        if not isinstance(step, dict):
            issues.append("workflow steps must be objects")
            continue
        expected = {"step_id", "step_sha256", "position", "kind", "capability", "mandatory", "depends_on", "consumes", "produces", "status", "blockers", "model_job", "route_decision"}
        if set(step) != expected:
            issues.append("workflow step fields do not match the contract")
            continue
        if step["step_id"] in ids:
            issues.append("workflow step identifiers must be unique")
        ids.add(step["step_id"])
        dependencies[step["step_id"]] = tuple(step["depends_on"])
        provisional = {key: step[key] for key in step if key != "step_sha256"}
        if step["step_sha256"] != _digest(provisional):
            issues.append(f"workflow step hash does not match:{step['step_id']}")
    try:
        order = _topological_order(dependencies)
        positions = tuple(step["step_id"] for step in sorted(value["steps"], key=lambda item: item["position"]))
        if positions != order:
            issues.append("workflow step order is not topological")
    except ValueError as exc:
        issues.append(str(exc))
    provisional = {key: value[key] for key in value if key != "workflow_sha256"}
    if value["workflow_sha256"] != _digest(provisional):
        issues.append("workflow plan hash does not match")
    return tuple(sorted(set(issues)))


def workflow_rerun_plan(plan: dict[str, Any], changed_inputs: list[str]) -> dict[str, Any]:
    issues = validate_workflow_plan(plan)
    if issues:
        raise ValueError("invalid workflow plan: " + "; ".join(issues))
    changed = set(_strings(changed_inputs, "changed_inputs", required=True))
    dependencies = {step["step_id"]: set(step["depends_on"]) for step in plan["steps"]}
    impacted = {step["step_id"] for step in plan["steps"] if changed.intersection(step["consumes"])}
    changed_flag = True
    while changed_flag:
        changed_flag = False
        for step_id, parents in dependencies.items():
            if step_id not in impacted and parents.intersection(impacted):
                impacted.add(step_id)
                changed_flag = True
    reusable = sorted(step["step_id"] for step in plan["steps"] if step["step_id"] not in impacted)
    provisional = {
        "contract_version": "workflow-rerun-plan.v1",
        "workflow_id": plan["workflow_id"],
        "workflow_sha256": plan["workflow_sha256"],
        "changed_inputs": sorted(changed),
        "invalidated_steps": sorted(impacted),
        "reusable_steps": reusable,
    }
    return {**provisional, "rerun_sha256": _digest(provisional)}


def execute_workflow(
    plan: dict[str, Any],
    *,
    idempotency_key: str,
    output_dir: str | Path,
    approvals: dict[str, bool] | None = None,
    orchestrator: ExecutionOrchestrator | None = None,
) -> dict[str, Any]:
    issues = validate_workflow_plan(plan)
    if issues:
        raise ValueError("invalid workflow plan: " + "; ".join(issues))
    key = _non_empty_string(idempotency_key, "idempotency_key")
    approval_map = approvals or {}
    if not isinstance(approval_map, dict) or not all(isinstance(name, str) and isinstance(value, bool) for name, value in approval_map.items()):
        raise ValueError("approvals must be an object of boolean decisions")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    engine = orchestrator or ExecutionOrchestrator(ledger=SqliteExecutionLedger(root / ".fmr-execution-ledger.sqlite3"))
    results: dict[str, dict[str, Any]] = {}
    for step in sorted(plan["steps"], key=lambda item: item["position"]):
        dependencies = [results[parent] for parent in step["depends_on"]]
        dependency_failed = any(item["state"] not in {"completed", "approved"} for item in dependencies)
        if dependency_failed:
            state = "blocked"
            details = ["dependency_not_completed"]
            execution_result = None
        elif step["status"] == "blocked":
            state = "blocked"
            details = list(step["blockers"])
            execution_result = None
        elif step["kind"] == "human_gate":
            decision = approval_map.get(step["step_id"])
            state = "approved" if decision is True else "rejected" if decision is False else "awaiting_approval"
            details = [] if decision is True else ["approval_rejected"] if decision is False else ["approval_required"]
            execution_result = None
        elif step["kind"] in {"internal", "assembly"}:
            state = "completed"
            details = []
            execution_result = None
        else:
            handoff = prepare_handoff(step["model_job"], policy_name=plan["request"]["policy_name"])
            execution_result = engine.execute(
                handoff,
                idempotency_key=f"{key}:{step['step_id']}:{step['step_sha256'][:12]}",
                output_dir=root / step["step_id"],
            )
            state = execution_result["state"]
            details = list(execution_result.get("errors_and_blockers", []))
        provisional = {
            "step_id": step["step_id"],
            "step_sha256": step["step_sha256"],
            "state": state,
            "details": details,
            "execution_result": execution_result,
        }
        results[step["step_id"]] = {**provisional, "result_sha256": _digest(provisional)}
    mandatory = [results[step["step_id"]] for step in plan["steps"] if step["mandatory"]]
    if any(item["state"] in {"failed", "rejected"} for item in mandatory):
        state = "failed"
    elif any(item["state"] == "blocked" for item in mandatory):
        state = "blocked"
    elif any(item["state"] == "awaiting_approval" for item in mandatory):
        state = "awaiting_approval"
    else:
        state = "completed"
    provisional = {
        "contract_version": "workflow-execution-result.v1",
        "workflow_id": plan["workflow_id"],
        "workflow_sha256": plan["workflow_sha256"],
        "state": state,
        "step_results": [results[step["step_id"]] for step in sorted(plan["steps"], key=lambda item: item["position"])],
        "idempotency_key_sha256": hashlib.sha256(key.encode("utf-8")).hexdigest(),
    }
    return {**provisional, "workflow_execution_id": f"fmrwx_{_digest(provisional)[:24]}"}


__all__ = [
    "BUILTIN_WORKFLOW_BLUEPRINTS",
    "WorkflowRequest",
    "builtin_workflow_blueprints",
    "compile_workflow",
    "execute_workflow",
    "validate_workflow_plan",
    "workflow_rerun_plan",
]
