const workflowObjective = document.querySelector("#workflow-objective");
const workflowRole = document.querySelector("#workflow-role");
const workflowTemplate = document.querySelector("#workflow-template");
const workflowOutputs = document.querySelector("#workflow-outputs");
const workflowData = document.querySelector("#workflow-data");
const workflowAssumptions = document.querySelector("#workflow-assumptions");
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
  operating_valuation: {
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

function splitValues(value) {
  return value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
}

function applyWorkflowExample() {
  const example = workflowExamples[workflowTemplate.value];
  workflowObjective.value = example.objective;
  workflowRole.value = example.role;
  workflowOutputs.value = example.requested_outputs.join(", ");
  workflowData.value = example.available_data.join(", ");
  workflowAssumptions.value = example.available_assumptions.join(", ");
  workflowStatus.textContent = "";
}

function buildWorkflowRequest() {
  const objective = workflowObjective.value.trim();
  if (!objective) throw new Error("Describe the finance work that needs to be completed.");
  const requestedOutputs = splitValues(workflowOutputs.value);
  if (!requestedOutputs.length) throw new Error("Provide at least one required output.");
  return {
    contract_version: "finance-workflow-request.v1",
    objective,
    role: workflowRole.value,
    entity_id: "company-a",
    reporting_period: "2026-06",
    requested_outputs: requestedOutputs,
    available_data: splitValues(workflowData.value),
    available_assumptions: splitValues(workflowAssumptions.value),
    input_references: {},
    industry: null,
    output_formats: ["json"],
    policy_name: "default",
    constraints: { local_only: true, open_source_only: true, network_allowed: false },
    context: {},
  };
}

async function compilePractitionerWorkflow() {
  workflowStatus.textContent = "";
  try {
    const plan = await requestJson("/api/v2/workflows/plans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildWorkflowRequest()),
    });
    showResult("Practitioner workflow plan", plan);
    const blocked = plan.steps.filter((step) => step.status === "blocked");
    const approvals = plan.steps.filter((step) => step.status === "awaiting_approval");
    const parts = [`${plan.steps.length} ordered steps`];
    if (blocked.length) parts.push(`${blocked.length} blocked`);
    if (approvals.length) parts.push(`${approvals.length} approval gate${approvals.length === 1 ? "" : "s"}`);
    workflowStatus.textContent = `Compiled ${plan.blueprint.blueprint_id}: ${parts.join(", ")}. Upload or connect a governed financial source to clear source-validation blockers.`;
  } catch (error) {
    workflowStatus.textContent = error.message;
  }
}

workflowTemplate.addEventListener("change", applyWorkflowExample);
document.querySelector("#compile-workflow-button").addEventListener("click", compilePractitionerWorkflow);
applyWorkflowExample();
