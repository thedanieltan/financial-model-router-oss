const workflowObjective = document.querySelector("#workflow-objective");
const workflowRole = document.querySelector("#workflow-role");
const workflowExample = document.querySelector("#workflow-example");
const workflowRequestEditor = document.querySelector("#workflow-request-editor");
const workflowStatus = document.querySelector("#workflow-status");

const workflowExamples = {
  monthly_forecast: {
    objective: "Update the full year forecast using June actuals",
    role: "fp_and_a",
    requested_outputs: ["rolling_forecast", "cash_outlook", "management_pack"],
    available_data: ["balance_sheet_history", "capital_expenditure", "cash_flow_history", "debt_schedule", "income_statement_history", "operating_cost_drivers", "revenue_drivers", "working_capital"],
    available_assumptions: ["capital_expenditure_rate", "depreciation_rate", "forecast_horizon", "operating_cost_growth_rate", "operating_margin_rate", "revenue_growth_rate", "scenario", "scenario_adjustments", "tax_rate", "working_capital_rate"],
  },
  debt_capacity: {
    objective: "Refresh debt capacity, leverage and covenant headroom",
    role: "finance_manager",
    requested_outputs: ["debt_capacity", "refinancing_analysis", "covenant_headroom"],
    available_data: ["cash_flow_history", "debt_schedule", "income_statement_history", "liquidity_position"],
    available_assumptions: ["annual_repayment", "covenant_thresholds", "ebitda_growth_rate", "forecast_horizon", "interest_rate_assumption", "maximum_leverage_ratio", "minimum_debt_service_coverage", "opening_debt", "repayment_terms"],
  },
  valuation: {
    objective: "Value the operating company using a DCF and show enterprise and equity value",
    role: "private_equity",
    requested_outputs: ["enterprise_value", "equity_value", "operating_company_dcf"],
    available_data: ["capital_expenditure", "cash_flow_history", "income_statement_history", "net_debt", "revenue_drivers", "working_capital"],
    available_assumptions: ["capital_expenditure_rate", "depreciation_rate", "discount_rate", "forecast_horizon", "net_debt", "operating_margin_rate", "revenue_growth_rate", "tax_rate", "terminal_growth_rate", "terminal_value_assumption", "working_capital_rate"],
  },
  project_finance: {
    objective: "Size and sculpt project finance debt to DSCR and LLCR targets",
    role: "project_finance",
    requested_outputs: ["debt_sizing", "debt_sculpting", "dscr", "llcr", "plcr"],
    available_data: ["project_cash_flow", "construction_schedule", "debt_terms"],
    available_assumptions: ["coverage_targets"],
  },
};

function workflowRequestFromExample(example) {
  return {
    contract_version: "finance-workflow-request.v1",
    objective: example.objective,
    role: example.role,
    entity_id: "company-a",
    reporting_period: "2026-06",
    requested_outputs: example.requested_outputs,
    available_data: example.available_data,
    available_assumptions: example.available_assumptions,
    input_references: {},
    industry: null,
    output_formats: ["json"],
    policy_name: "default",
    constraints: { local_only: true, open_source_only: true, network_allowed: false },
    context: {},
  };
}

function applyWorkflowExample() {
  const example = workflowExamples[workflowExample.value];
  const request = workflowRequestFromExample(example);
  workflowObjective.value = request.objective;
  workflowRole.value = request.role;
  workflowRequestEditor.value = JSON.stringify(request, null, 2);
}

function synchronizeWorkflowFields() {
  try {
    const request = JSON.parse(workflowRequestEditor.value);
    request.objective = workflowObjective.value.trim();
    request.role = workflowRole.value;
    workflowRequestEditor.value = JSON.stringify(request, null, 2);
  } catch (_error) {
    workflowStatus.textContent = "Workflow request JSON must be valid before fields can be synchronized.";
  }
}

async function compilePractitionerWorkflow() {
  workflowStatus.textContent = "";
  try {
    synchronizeWorkflowFields();
    const request = JSON.parse(workflowRequestEditor.value);
    const plan = await requestJson("/api/v2/workflows/plans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    showResult("Practitioner workflow plan", plan);
    const blocked = plan.steps.filter((step) => step.status === "blocked");
    const approval = plan.steps.filter((step) => step.status === "awaiting_approval");
    const summaryParts = [`${plan.steps.length} ordered steps`];
    if (blocked.length) summaryParts.push(`${blocked.length} blocked`);
    if (approval.length) summaryParts.push(`${approval.length} approval gate${approval.length === 1 ? "" : "s"}`);
    workflowStatus.textContent = `Compiled ${plan.blueprint.blueprint_id}: ${summaryParts.join(", ")}.`;
  } catch (error) {
    workflowStatus.textContent = error.message;
  }
}

workflowExample.addEventListener("change", applyWorkflowExample);
workflowObjective.addEventListener("change", synchronizeWorkflowFields);
workflowRole.addEventListener("change", synchronizeWorkflowFields);
document.querySelector("#compile-workflow-button").addEventListener("click", compilePractitionerWorkflow);
applyWorkflowExample();
