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
let workflowPlan = null;
let workflowProject = null;

const workflowExamples = {
  monthly_forecast: {
    objective: "Update the full year forecast using June actuals",
    role: "fp_and_a",
    requested_outputs: ["rolling_forecast", "cash_outlook", "management_pack"],
    available_data: ["operating_cost_drivers", "revenue_drivers"],
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
    available_data: ["debt_schedule"],
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
    available_data: ["net_debt", "revenue_drivers"],
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

function createProjectControls() {
  const wrapper = document.createElement("div");
  wrapper.id = "workflow-project-controls";
  wrapper.innerHTML = `
    <div class="panel-heading">
      <div>
        <h3>Save, run and review</h3>
        <p>Projects retain the workflow plan, approval decisions and value-free receipts locally so work can be reopened.</p>
      </div>
    </div>
    <div class="workbook-control">
      <label for="workflow-project-name">Project name</label>
      <input id="workflow-project-name" type="text" maxlength="160" placeholder="FY2027 rolling forecast">
      <button id="save-workflow-project-button" type="button" class="secondary" disabled>Save project</button>
      <button id="run-workflow-project-button" type="button" disabled>Run ready steps</button>
    </div>
    <div class="workbook-control">
      <label for="workflow-project-select">Reopen project</label>
      <select id="workflow-project-select"><option value="">No saved project selected</option></select>
      <button id="refresh-workflow-projects-button" type="button" class="quiet">Refresh</button>
    </div>
    <div id="workflow-approval-gates"></div>
    <div class="actions">
      <button id="approve-workflow-project-button" type="button" class="secondary" disabled>Approve selected gates and continue</button>
    </div>
    <p id="workflow-project-status" class="status" aria-live="polite"></p>
  `;
  workflowStatus.insertAdjacentElement("afterend", wrapper);
  document.querySelector("#save-workflow-project-button").addEventListener("click", saveWorkflowProject);
  document.querySelector("#run-workflow-project-button").addEventListener("click", runWorkflowProject);
  document.querySelector("#approve-workflow-project-button").addEventListener("click", approveWorkflowProject);
  document.querySelector("#refresh-workflow-projects-button").addEventListener("click", refreshWorkflowProjects);
  document.querySelector("#workflow-project-select").addEventListener("change", loadSelectedWorkflowProject);
}

function projectStatus(message) {
  document.querySelector("#workflow-project-status").textContent = message;
}

function renderApprovalGates(project) {
  const container = document.querySelector("#workflow-approval-gates");
  const gates = project.plan.steps.filter((step) => step.kind === "human_gate");
  if (!gates.length) {
    container.innerHTML = "";
    document.querySelector("#approve-workflow-project-button").disabled = true;
    return;
  }
  container.innerHTML = `<p><strong>Approval gates</strong></p>${gates.map((gate) => {
    const checked = project.approvals[gate.step_id] === true ? " checked" : "";
    return `<label><input type="checkbox" data-workflow-gate="${gate.step_id}"${checked}> Approve ${gate.capability.replaceAll("_", " ")}</label>`;
  }).join("<br>")}`;
  document.querySelector("#approve-workflow-project-button").disabled = false;
}

function renderWorkflowProject(project) {
  workflowProject = project;
  workflowPlan = project.plan;
  document.querySelector("#workflow-project-name").value = project.name;
  document.querySelector("#save-workflow-project-button").disabled = false;
  document.querySelector("#run-workflow-project-button").disabled = false;
  renderApprovalGates(project);
  const latest = project.latest_execution;
  const suffix = latest ? ` Latest run: ${latest.state}.` : " No run has been recorded.";
  projectStatus(`${project.name} · ${project.status} · version ${project.version}.${suffix}`);
  showResult("Workflow project", project);
}

async function refreshWorkflowProjects() {
  try {
    const result = await requestJson("/api/v2/workflow-projects");
    const select = document.querySelector("#workflow-project-select");
    const selected = workflowProject ? workflowProject.project_id : select.value;
    select.innerHTML = '<option value="">No saved project selected</option>' + result.projects.map((project) =>
      `<option value="${project.project_id}">${project.name} · ${project.status}</option>`
    ).join("");
    select.value = result.projects.some((project) => project.project_id === selected) ? selected : "";
  } catch (error) {
    projectStatus(error.message);
  }
}

async function loadSelectedWorkflowProject() {
  const projectId = document.querySelector("#workflow-project-select").value;
  if (!projectId) return;
  try {
    renderWorkflowProject(await requestJson(`/api/v2/workflow-projects/${projectId}`));
  } catch (error) {
    projectStatus(error.message);
  }
}

async function saveWorkflowProject() {
  try {
    if (!workflowPlan) throw new Error("Build a workflow before saving a project.");
    const name = document.querySelector("#workflow-project-name").value.trim() || workflowObjective.value.trim();
    const project = await requestJson("/api/v2/workflow-projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, plan: workflowPlan }),
    });
    renderWorkflowProject(project);
    await refreshWorkflowProjects();
    document.querySelector("#workflow-project-select").value = project.project_id;
  } catch (error) {
    projectStatus(error.message);
  }
}

async function ensureWorkflowProject() {
  if (workflowProject && workflowPlan && workflowProject.workflow_sha256 === workflowPlan.workflow_sha256) return workflowProject;
  await saveWorkflowProject();
  if (!workflowProject) throw new Error("The workflow project could not be saved.");
  return workflowProject;
}

async function runWorkflowProject() {
  try {
    const project = await ensureWorkflowProject();
    projectStatus("Executing dependency-ready steps…");
    const updated = await requestJson(`/api/v2/workflow-projects/${project.project_id}/executions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: project.version }),
    });
    renderWorkflowProject(updated);
    await refreshWorkflowProjects();
  } catch (error) {
    projectStatus(error.message);
  }
}

async function approveWorkflowProject() {
  try {
    const project = await ensureWorkflowProject();
    const decisions = {};
    document.querySelectorAll("[data-workflow-gate]").forEach((input) => {
      if (input.checked) decisions[input.dataset.workflowGate] = true;
    });
    if (!Object.keys(decisions).length) throw new Error("Select at least one approval gate.");
    const approved = await requestJson(`/api/v2/workflow-projects/${project.project_id}/approvals`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decisions, expected_version: project.version }),
    });
    workflowProject = approved;
    projectStatus("Approval recorded. Completing the workflow with accepted provider results…");
    const completed = await requestJson(`/api/v2/workflow-projects/${project.project_id}/executions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: approved.version }),
    });
    renderWorkflowProject(completed);
    await refreshWorkflowProjects();
  } catch (error) {
    projectStatus(error.message);
  }
}

function applyWorkflowExample() {
  const example = workflowExamples[workflowTemplate.value];
  workflowSource = null;
  workflowPlan = null;
  workflowProject = null;
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
  document.querySelector("#workflow-project-name").value = example.objective;
  document.querySelector("#save-workflow-project-button").disabled = true;
  document.querySelector("#run-workflow-project-button").disabled = true;
  document.querySelector("#approve-workflow-project-button").disabled = true;
  document.querySelector("#workflow-approval-gates").innerHTML = "";
  projectStatus("");
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
    workflowPlan = null;
    workflowProject = null;
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
    policy_name: "json-first",
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
    workflowPlan = plan;
    workflowProject = null;
    showResult("Practitioner workflow plan", plan);
    const blocked = plan.steps.filter((step) => step.status === "blocked");
    const approvals = plan.steps.filter((step) => step.status === "awaiting_approval");
    const parts = [`${plan.steps.length} ordered steps`];
    if (blocked.length) parts.push(`${blocked.length} blocked`);
    if (approvals.length) parts.push(`${approvals.length} approval gate${approvals.length === 1 ? "" : "s"}`);
    const sourceText = workflowSource ? ` Source ${workflowSource.source_id} is pinned.` : " No source is pinned, so source-dependent steps remain blocked.";
    workflowStatus.textContent = `Compiled ${plan.blueprint.blueprint_id}: ${parts.join(", ")}.${sourceText}`;
    document.querySelector("#workflow-project-name").value = workflowObjective.value.trim();
    document.querySelector("#save-workflow-project-button").disabled = false;
    document.querySelector("#run-workflow-project-button").disabled = false;
    renderApprovalGates({ plan, approvals: {} });
  } catch (error) {
    workflowStatus.textContent = error.message;
  }
}

createProjectControls();
workflowTemplate.addEventListener("change", applyWorkflowExample);
document.querySelector("#prepare-workflow-source-button").addEventListener("click", prepareWorkflowSource);
document.querySelector("#compile-workflow-button").addEventListener("click", compilePractitionerWorkflow);
applyWorkflowExample();
refreshWorkflowProjects();
