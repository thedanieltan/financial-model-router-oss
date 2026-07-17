from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fmr.financial_data import WorkflowSourceStore, create_statement_csv_workflow_source
from fmr.workflow import compile_workflow, execute_workflow


_PERIODS = ("2023-12-31", "2024-12-31", "2025-12-31")
_VALUES = {
    "Revenue": ("1000000", "1150000", "1300000"),
    "Operating costs": ("700000", "780000", "850000"),
    "EBITDA": ("300000", "370000", "450000"),
    "Cash": ("150000", "200000", "250000"),
    "Debt": ("400000", "350000", "300000"),
    "Accounts receivable": ("120000", "135000", "150000"),
    "Inventory": ("70000", "75000", "80000"),
    "Accounts payable": ("90000", "95000", "100000"),
    "Capital expenditure": ("50000", "60000", "70000"),
    "Operating cash flow": ("220000", "280000", "330000"),
}
_ROWS = (
    ("4000", "Revenue", "income_statement", "flow"),
    ("6000", "Operating costs", "income_statement", "flow"),
    ("6100", "EBITDA", "income_statement", "flow"),
    ("1000", "Cash", "balance_sheet", "point_in_time"),
    ("2000", "Debt", "balance_sheet", "point_in_time"),
    ("1100", "Accounts receivable", "balance_sheet", "point_in_time"),
    ("1200", "Inventory", "balance_sheet", "point_in_time"),
    ("2100", "Accounts payable", "balance_sheet", "point_in_time"),
    ("7000", "Capital expenditure", "cash_flow", "flow"),
    ("7100", "Operating cash flow", "cash_flow", "flow"),
)

_CASES: dict[str, dict[str, Any]] = {
    "monthly_forecast": {
        "objective": "Update the full year forecast using the latest actuals",
        "role": "fp_and_a",
        "requested_outputs": ["rolling_forecast", "management_pack"],
        "additional_data": [],
        "default_assumptions": {
            "forecast_horizon": 3,
            "operating_cost_growth_rate": "0.05",
            "revenue_growth_rate": "0.08",
            "scenario": "base",
            "scenario_adjustments": {
                "base": {
                    "operating_cost_growth_delta": "0",
                    "revenue_growth_delta": "0",
                }
            },
        },
    },
    "operating_valuation": {
        "objective": "Value the operating company using a discounted cash flow",
        "role": "private_equity",
        "requested_outputs": ["enterprise_value", "equity_value", "operating_company_dcf"],
        "additional_data": ["net_debt", "revenue_drivers"],
        "default_assumptions": {
            "capital_expenditure_rate": "0.05",
            "depreciation_rate": "0.03",
            "discount_rate": "0.10",
            "forecast_horizon": 5,
            "net_debt": "300000",
            "operating_margin_rate": "0.20",
            "revenue_growth_rate": "0.08",
            "tax_rate": "0.17",
            "terminal_growth_rate": "0.02",
            "terminal_value_assumption": "perpetuity_growth",
            "working_capital_rate": "0.10",
        },
    },
    "debt_capacity": {
        "objective": "Refresh debt capacity, leverage and covenant headroom",
        "role": "finance_manager",
        "requested_outputs": ["debt_capacity", "refinancing_analysis", "covenant_headroom"],
        "additional_data": ["debt_schedule"],
        "default_assumptions": {
            "annual_repayment": "75000",
            "covenant_thresholds": {},
            "ebitda_growth_rate": "0.05",
            "forecast_horizon": 4,
            "interest_rate_assumption": "0.05",
            "maximum_leverage_ratio": "3.0",
            "minimum_debt_service_coverage": "1.5",
            "opening_debt": "300000",
            "repayment_terms": "annual",
        },
    },
    "project_finance": {
        "objective": "Size and sculpt project finance debt to DSCR and LLCR targets",
        "role": "project_finance",
        "requested_outputs": ["debt_sizing", "debt_sculpting", "dscr", "llcr", "plcr"],
        "additional_data": ["construction_schedule", "debt_terms", "project_cash_flow"],
        "default_assumptions": {"coverage_targets": {"dscr": "1.30", "llcr": "1.50"}},
    },
}


def _statement_csv() -> bytes:
    header = (
        "entity_id,entity_name,currency,period_end,period_type,statement_type,"
        "balance_type,account_code,account_name,amount,source_ref"
    )
    lines = [header]
    for period_index, period in enumerate(_PERIODS):
        for code, name, statement_type, balance_type in _ROWS:
            lines.append(
                ",".join(
                    (
                        "fmr-demo-co",
                        "FMR Demo Company",
                        "SGD",
                        period,
                        "actual",
                        statement_type,
                        balance_type,
                        code,
                        name,
                        _VALUES[name][period_index],
                        f"synthetic:{period}:{code}",
                    )
                )
            )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _source(assumptions: dict[str, Any]) -> dict[str, Any]:
    operational_drivers = {
        "revenue_units": ["10000", "11200", "12500"],
        "headcount": ["20", "23", "25"],
    }
    return create_statement_csv_workflow_source(
        _statement_csv(),
        source_name="fmr-pages-synthetic-case.csv",
        assumptions=assumptions,
        operational_drivers=operational_drivers,
        store=WorkflowSourceStore("/tmp/fmr-pages-sources"),
    )


def _model_artifact(execution: dict[str, Any]) -> dict[str, Any] | None:
    for step in execution.get("step_results", []):
        result = step.get("execution_result")
        if not isinstance(result, dict):
            continue
        for artifact in result.get("provider_receipt", {}).get("output_artifacts", []):
            path = artifact.get("path")
            if artifact.get("format") == "json" and isinstance(path, str):
                return json.loads(Path(path).read_text(encoding="utf-8"))
    return None


def _summary(plan: dict[str, Any]) -> dict[str, Any]:
    routes = []
    for step in plan["steps"]:
        route = step.get("route_decision")
        selected = route.get("selected") if isinstance(route, dict) else None
        routes.append(
            {
                "step_id": step["step_id"],
                "kind": step["kind"],
                "status": step["status"],
                "blockers": step["blockers"],
                "provider_id": selected.get("provider_id") if isinstance(selected, dict) else None,
                "package_id": selected.get("package_id") if isinstance(selected, dict) else None,
            }
        )
    return {
        "workflow_id": plan["workflow_id"],
        "blueprint": plan["blueprint"],
        "status": plan["status"],
        "missing_requirements": plan["missing_requirements"],
        "steps": routes,
    }


def run_demo(payload: dict[str, Any], *, execute: bool) -> dict[str, Any]:
    case_id = payload.get("case_id")
    if case_id not in _CASES:
        raise ValueError("unknown demo case")
    case = _CASES[case_id]
    assumptions = dict(case["default_assumptions"])
    supplied = payload.get("assumptions", {})
    if not isinstance(supplied, dict):
        raise ValueError("assumptions must be an object")
    assumptions.update(supplied)
    source = _source(assumptions)
    available_data = sorted(set(source["available_data"]) | set(case["additional_data"]))
    request = {
        "contract_version": "finance-workflow-request.v1",
        "objective": case["objective"],
        "role": case["role"],
        "entity_id": source["entity"]["entity_id"],
        "reporting_period": source["periods"][-1],
        "requested_outputs": case["requested_outputs"],
        "available_data": available_data,
        "available_assumptions": sorted(assumptions),
        "input_references": {"canonical_financial_data": source["canonical_reference"]},
        "industry": None,
        "output_formats": ["json"],
        "policy_name": "json-first",
        "constraints": {
            "local_only": True,
            "network_allowed": False,
            "open_source_only": True,
        },
        "context": {"demo": True, "source_id": source["source_id"]},
    }
    plan = compile_workflow(request)
    response: dict[str, Any] = {
        "case_id": case_id,
        "source": {
            "entity": source["entity"],
            "periods": source["periods"],
            "available_data": available_data,
            "warning_count": len(source["warnings"]),
        },
        "plan": _summary(plan),
        "execution": None,
        "artifact": None,
        "boundary": {
            "browser_only": True,
            "synthetic_data": True,
            "production_accepted": False,
            "workbook_execution_available": False,
        },
    }
    if execute and plan["status"] != "blocked":
        approvals = {
            step["step_id"]: True
            for step in plan["steps"]
            if step["kind"] == "human_gate"
        }
        execution = execute_workflow(
            plan,
            idempotency_key=f"pages-{case_id}-{uuid.uuid4().hex}",
            output_dir=f"/tmp/fmr-pages-output/{uuid.uuid4().hex}",
            approvals=approvals,
        )
        response["execution"] = {
            "state": execution["state"],
            "workflow_execution_id": execution["workflow_execution_id"],
            "steps": [
                {
                    "step_id": step["step_id"],
                    "state": step["state"],
                    "details": step["details"],
                }
                for step in execution["step_results"]
            ],
        }
        response["artifact"] = _model_artifact(execution)
    return response


def run_demo_json(payload_json: str, execute: bool = False) -> str:
    payload = json.loads(payload_json)
    return json.dumps(run_demo(payload, execute=execute), sort_keys=True)
