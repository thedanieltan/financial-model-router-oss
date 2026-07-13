from fmr.model_specs import MODEL_BY_FAMILY
from fmr.router import route_request
from fmr.types import ModelRequest, TransformationOperation, TransformationPlan

_ALLOWED_OPERATIONS = {
    "preserve_existing_workbook", "create_assumptions_section", "add_forecast_periods",
    "create_revenue_schedule", "create_operating_cost_schedule", "create_working_capital_schedule",
    "create_capital_expenditure_schedule", "create_debt_schedule", "create_interest_schedule",
    "create_cash_sweep_schedule", "create_covenant_schedule", "create_refinancing_scenarios",
    "link_financial_statements", "extend_operating_forecast", "create_free_cash_flow_schedule",
    "create_discount_factor_schedule", "create_terminal_value_section", "create_enterprise_to_equity_bridge",
    "add_valuation_sensitivity", "add_integrity_checks", "add_balance_checks", "add_cash_flow_checks",
    "add_liquidity_checks", "request_missing_inputs",
}


def build_plan(request: ModelRequest) -> TransformationPlan:
    recommendation = route_request(request)
    definition = MODEL_BY_FAMILY[recommendation.model_family]
    readiness = recommendation.readiness
    operations: list[TransformationOperation] = []
    sequence = 1
    if not readiness.ready:
        operations.append(TransformationOperation(sequence=sequence, operation="request_missing_inputs", target="request", rationale="Resolve all readiness blockers before workbook mutation."))
        sequence += 1
    for operation in definition.operations:
        if operation not in _ALLOWED_OPERATIONS:
            raise ValueError(f"unsupported operation in model definition: {operation}")
        operations.append(TransformationOperation(sequence=sequence, operation=operation, target="workbook", rationale=f"Required by {definition.model_family}."))
        sequence += 1
    return TransformationPlan(
        contract_version="transformation-plan.v1",
        model_family=definition.model_family,
        ready_to_apply=readiness.ready,
        operations=tuple(operations),
        unresolved_inputs=tuple(readiness.blockers),
        controls=("do_not_overwrite_source_workbook", "do_not_invent_missing_inputs", "approved_operations_only", "formula_and_cell_writes_require_separate_validation"),
    )


def validate_plan_payload(payload: dict) -> tuple[str, ...]:
    issues: list[str] = []
    if payload.get("contract_version") != "transformation-plan.v1":
        issues.append("unsupported contract_version")
    operations = payload.get("operations")
    if not isinstance(operations, list):
        issues.append("operations must be an array")
        return tuple(issues)
    seen_sequences: set[int] = set()
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            issues.append(f"operations[{index}] must be an object")
            continue
        if operation.get("operation") not in _ALLOWED_OPERATIONS:
            issues.append(f"operations[{index}].operation is not allowed")
        sequence = operation.get("sequence")
        if not isinstance(sequence, int) or sequence < 1:
            issues.append(f"operations[{index}].sequence must be a positive integer")
        elif sequence in seen_sequences:
            issues.append(f"operations[{index}].sequence is duplicated")
        else:
            seen_sequences.add(sequence)
        if {"formula", "cell", "cell_write", "workbook_bytes"}.intersection(operation):
            issues.append(f"operations[{index}] contains executable workbook fields")
    return tuple(issues)
