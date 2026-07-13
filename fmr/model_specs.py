from fmr.types import ModelDefinition


MODEL_DEFINITIONS: tuple[ModelDefinition, ...] = (
    ModelDefinition(
        model_family="budget_forecast",
        title="Budget and forecast",
        objective_terms=("budget", "forecast", "financial plan", "runway"),
        required_data=("income_statement_history", "balance_sheet_history", "revenue_drivers", "operating_cost_drivers"),
        required_assumptions=("forecast_horizon",),
        required_workbook_capabilities=("historical_periods",),
        operations=("preserve_existing_workbook", "create_assumptions_section", "add_forecast_periods", "create_revenue_schedule", "create_operating_cost_schedule", "add_integrity_checks"),
    ),
    ModelDefinition(
        model_family="three_statement",
        title="Integrated three-statement model",
        objective_terms=("three statement", "three-statement", "integrated model", "financial statements"),
        required_data=("income_statement_history", "balance_sheet_history", "cash_flow_history", "capital_expenditure_schedule", "working_capital_schedule", "debt_schedule"),
        required_assumptions=("forecast_horizon", "tax_rate"),
        required_workbook_capabilities=("historical_periods",),
        operations=("preserve_existing_workbook", "create_assumptions_section", "add_forecast_periods", "create_revenue_schedule", "create_operating_cost_schedule", "create_working_capital_schedule", "create_capital_expenditure_schedule", "create_debt_schedule", "link_financial_statements", "add_balance_checks", "add_cash_flow_checks"),
    ),
    ModelDefinition(
        model_family="operating_company_dcf",
        title="Operating-company discounted cash-flow valuation",
        objective_terms=("dcf", "discounted cash flow", "value an operating company", "valuation"),
        required_data=("income_statement_history", "balance_sheet_history", "cash_flow_history", "revenue_drivers", "capital_expenditure_schedule", "working_capital_schedule", "net_debt"),
        required_assumptions=("forecast_horizon", "tax_rate", "discount_rate", "terminal_value_assumption"),
        required_workbook_capabilities=("historical_periods", "assumptions_section"),
        operations=("preserve_existing_workbook", "extend_operating_forecast", "create_free_cash_flow_schedule", "create_discount_factor_schedule", "create_terminal_value_section", "create_enterprise_to_equity_bridge", "add_valuation_sensitivity", "add_integrity_checks"),
    ),
    ModelDefinition(
        model_family="debt_capacity_refinancing",
        title="Debt-capacity and refinancing analysis",
        objective_terms=("debt capacity", "refinancing", "refinance", "covenant", "leverage"),
        required_data=("income_statement_history", "cash_flow_history", "debt_schedule", "liquidity_position"),
        required_assumptions=("forecast_horizon", "interest_rate_assumption", "repayment_terms", "covenant_thresholds"),
        required_workbook_capabilities=("historical_periods",),
        operations=("preserve_existing_workbook", "create_debt_schedule", "create_interest_schedule", "create_cash_sweep_schedule", "create_covenant_schedule", "create_refinancing_scenarios", "add_liquidity_checks"),
    ),
)

MODEL_BY_FAMILY = {definition.model_family: definition for definition in MODEL_DEFINITIONS}
