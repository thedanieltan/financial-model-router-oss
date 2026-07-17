const workflowObjective = document.querySelector("#workflow-objective");
const workflowRole = document.querySelector("#workflow-role");
const workflowTemplate = document.querySelector("#workflow-template");
const workflowOutputs = document.querySelector("#workflow-outputs");
const workflowData = document.querySelector("#workflow-data");
const workflowAssumptions = document.querySelector("#workflow-assumptions");
const workflowAssumptionValues = document.querySelector("#workflow-assumption-values");
const workflowOperationalDrivers = document.querySelector("#workflow-operational-drivers");
const workflowMappingRules = document.querySelector("#workflow-mapping-rules");
const workflowSourceFile = document.querySelector("#workflow-source-file");
const workflowSourceStatus = document.querySelector("#workflow-source-status");
const workflowStatus = document.querySelector("#workflow-status");

let workflowSource = null;

const workflowExamples = {
  monthly_forecast: {
    objective: "Update the full year forecast using June actuals",
    role: "fp_and_a",
    requested_outputs: ["rolling_forecast", "cash_outlook", "management_pack"],
    available_data: ["balance_sheet_history", "capital_expenditure", "cash_flow_history", "debt_schedule", "income_statement_history", "operating_cost_drivers", "revenue_drivers", "working_capital"],
    assumptions: {
      capital_expenditure_rate: "0.05",
      depreciation_rate: "0.03",
      forecast_horizon: 3,
      operating_cost_growth_rate: "0.05",
      operating_margin_rate: "0.20",
      revenue_growth_rate: "0.08",
      scenario: "base",
      scenario_adjustments: { base: { revenue_growth_delta: "0", operating_cost_growth_delta: "0" } },
      tax_rate: "0.17",
      working_capital_rate: "0.10",
    },
  },
  debt_capacity: {
    objective: "Refresh debt capacity, leverage and covenant headroom",
    role: "finance_manager",
    requested_outputs: ["debt_capacity", "refinancing_analysis", "covenant_headroom"],
    available_data: ["cash_flow_history", "debt_schedule", "income_statement_history", "liquidity_position"],
    assumptions: {
      annual_repayment: "50000",
      covenant_thresholds: {},
      ebitda_growth_rate: "0.05",
      forecast_horizon: 3,
      interest_rate_assumption: "0.05",
      maximum_leverage_ratio: "3.0",
      minimum_debt_service_coverage: "1.5",
      opening_debt: "200000",
      repayment_terms: "annual",
    },
  },
  operating_valuation: {
    objective: "Value the operating company using a DCF and show enterprise and equity value",
    role: "private_equity",
    requested_outputs: ["enterprise_value", "equity_value", "operating_company_dcf"],
    available_data: ["capital_expenditure", "cash_flow_history", "income_statement_history", "net_debt", "revenue_drivers", "working_capital"],
    assumptions: {
      capital_expenditure_rate: "0.05",
      depreciation_rate: "0.03",
      discount_rate: "0.10",
      forecast_horizon: 5,
      net_debt: "200000",
      operating_margin_rate: "0.20",
      revenue_growth_rate: "0.08",
      tax_rate: "0.17",
      terminal_growth_rate: "0.02",
      terminal_value_assumption: "perpetuity_growth",
      working_capital_rate: "0.10",
    },
  },
  project_finance: {
    objective: "Size and sculpt project finance debt to DSCR and LLCR targets",
    role: "project_finance",
    requested_outputs: ["debt_sizing", "debt_sculpting", "dscr", "llcr", "plcr"],
    available_data: ["project_cash_flow", "construction_schedule", "debt_terms"],
    assumptions: { coverage_targets: { dscr: "1.30", llcr: "1.50" } },
  },
};

function splitValues(value) {
  return value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
}

function unionValues(...groups) {
  return [...new Set(groups.flat().filter(Boolean))].sort();
}

function parseObject(editor, label) {
  try {
    const value = JSON.parse(editor.value || "{}");
    if (!value || Array.isArray(value) || typeof value !== "object") throw new Error();
    return value;
  } catch (_error) {
    throw new Error(`${label} must be a valid JSON object.`);
  }
}

function parseArray(editor, label) {
  try {
    const value = JSON.parse(editor.value || "[]");
    if (!Array.isArray(value)) throw new Error();
    return value;
  } catch (_error) {
    throw new Error(`${label} must be a valid JSON array.`);
  }
}

async function fileBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const chunk = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunk) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunk));
  }
  return btoa(binary);
}

function applyWorkflowExample() {
  const example = workflowExamples[workflowTemplate.value];
  workflowSource = null;
  workflowSourceFile.value = "";
  workflowSourceStatus.textContent = "No financial source prepared.";
  workflowObjective.value = example.objective;
  workflowRole.value = example.role;
  workflowOutputs.value = example.requested_outputs.join(", ");
  workflowData.value = example.available_data.join(", ");
  workflowAssumptions.value = Object.keys(example.assumptions).sort().join(", ");
  workflowAssumptionValues.value = JSON.stringify(example.assumptions, null, 2);
  workflowOperationalDrivers.value = "{}";
  workflowMappingRules.value = "[]";
  workflowStatus.textContent = "";
}

async function prepareWorkflowSource() {
  workflowSourceStatus.textContent = "";
  try {
    const file = workflowSourceFile.files[0];
    if (!file) throw new Error("Select a statement CSV or download the template first.");
    const assumptions = parseObject(workflowAssumptionValues, "Assumption values");
    const operationalDrivers = parseObject(workflowOperationalDrivers, "Operational drivers");
    const mappingRules = parseArray(workflowMappingRules, "Mapping rules");
    workflowSourceStatus.textContent = "Validating, mapping and storing the financial source…";
    const source = await requestJson("/api/v2/workflow-sources/statement-csv", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contract_version: "workflow-statement-csv-request.v1",
        source_name: file.name,
        csv_base64: await fileBase64(file),
        mapping_rules: mappingRules,
        assumptions,
        operational_drivers: operationalDrivers,
      }),
    });
    workflowSource = source;
    workflowData.value = unionValues(splitValues(workflowData.value), source.available_data).join(", ");
    workflowAssumptions.value = unionValues(splitValues(workflowAssumptions.value), source.available_assumptions).join(", ");
    const warningText = source.warnings.length ? ` ${source.warnings.length} unmapped row warning(s) remain visible in the result.` : "";
    workflowSourceStatus.textContent = `Prepared ${source.entity.entity_name} with ${source.periods.length} period(s).${warningText}`;
    showResult("Workflow financial source", source);
  } catch (error) {
    workflowSource = null;
    workflowSourceStatus.textContent = error.message;
  }
}

function buildWorkflowRequest() {
  const objective = workflowObjective.value.trim();
  if (!objective) throw new Error("Describe the finance work that needs to be completed.");
  const requestedOutputs = splitValues(workflowOutputs.value);
  if (!requestedOutputs.length) throw new Error("Provide at least one required output.");
  const sourceData = workflowSource ? workflowSource.available_data : [];
  const sourceAssumptions = workflowSource ? workflowSource.available_assumptions : [];
  return {
    contract_version: "finance-workflow-request.v1",
    objective,
    role: workflowRole.value,
    entity_id: workflowSource ? workflowSource.entity.entity_id : "company-a",
    reporting_period: workflowSource ? workflowSource.periods.at(-1) : "2026-06",
    requested_outputs: requestedOutputs,
    available_data: unionValues(splitValues(workflowData.value), sourceData),
    available_assumptions: unionValues(splitValues(workflowAssumptions.value), sourceAssumptions),
    input_references: workflowSource ? { canonical_financial_data: workflowSource.canonical_reference } : {},
    industry: null,
    output_formats: ["json"],
    policy_name: "local-only",
    constraints: { local_only: true, open_source_only: true, network_allowed: false },
    context: workflowSource ? { workflow_source_id: workflowSource.source_id } : {},
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
    const sourceText = workflowSource ? ` Source ${workflowSource.source_id} is pinned.` : " No source is pinned, so source-dependent steps remain blocked.";
    workflowStatus.textContent = `Compiled ${plan.blueprint.blueprint_id}: ${parts.join(", ")}.${sourceText}`;
  } catch (error) {
    workflowStatus.textContent = error.message;
  }
}

workflowTemplate.addEventListener("change", applyWorkflowExample);
document.querySelector("#prepare-workflow-source-button").addEventListener("click", prepareWorkflowSource);
document.querySelector("#compile-workflow-button").addEventListener("click", compilePractitionerWorkflow);
applyWorkflowExample();
