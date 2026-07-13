const editor = document.querySelector("#request-editor");
const fixtureSelect = document.querySelector("#fixture-select");
const output = document.querySelector("#result-output");
const summary = document.querySelector("#summary");
const resultKind = document.querySelector("#result-kind");
const requestStatus = document.querySelector("#request-status");
const workbookStatus = document.querySelector("#workbook-status");
const workbookFile = document.querySelector("#workbook-file");
const analyseButton = document.querySelector("#analyse-button");
const compilePatchButton = document.querySelector("#compile-patch-button");
const resolveTargetsButton = document.querySelector("#resolve-targets-button");
const planCoordinatesButton = document.querySelector("#plan-coordinates-button");
const forecastPeriodCount = document.querySelector("#forecast-period-count");
const copyButton = document.querySelector("#copy-button");
const healthIndicator = document.querySelector("#health-indicator");

let currentFixture = null;
let currentResult = null;
let currentWorkbookMap = null;
let currentAnalysis = null;
let currentPatch = null;
let currentTargetResolution = null;
let currentCoordinatePlan = null;

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function parseEditor() {
  const value = JSON.parse(editor.value);
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new Error("Request JSON root must be an object.");
  }
  return value;
}

function parseForecastPeriodCount() {
  const value = Number(forecastPeriodCount.value);
  if (!Number.isInteger(value) || value < 1 || value > 60) {
    throw new Error("Forecast periods must be an integer between 1 and 60.");
  }
  return value;
}

function setStatus(message = "") {
  requestStatus.textContent = message;
}

function invalidateCoordinatePlan() {
  currentCoordinatePlan = null;
}

function invalidateAnalysis() {
  currentAnalysis = null;
  currentPatch = null;
  currentTargetResolution = null;
  currentCoordinatePlan = null;
  compilePatchButton.disabled = true;
  resolveTargetsButton.disabled = true;
  planCoordinatesButton.disabled = true;
}

function addSummaryCard(label, value) {
  const card = document.createElement("div");
  card.className = "card";
  const labelNode = document.createElement("span");
  labelNode.textContent = label;
  const valueNode = document.createElement("strong");
  valueNode.textContent = value;
  card.append(labelNode, valueNode);
  summary.append(card);
}

function renderSummary(payload) {
  const recommendation = payload.recommendation || payload;
  const readiness = recommendation.readiness || {};
  const workbookMap = payload.workbook_map
    || (payload.contract_version === "workbook-map.v1" ? payload : null);
  const workbook = workbookMap?.workbook || {};
  const source = workbookMap?.source || payload.source || {};
  const plan = payload.transformation_plan || payload;
  const evidence = payload.derived_evidence || {};
  const cards = [];

  if (recommendation.model_family) cards.push(["Model family", recommendation.model_family]);
  if (recommendation.confidence) cards.push(["Confidence", recommendation.confidence]);
  if (typeof readiness.ready === "boolean") cards.push(["Ready", readiness.ready ? "Yes" : "No"]);
  if (Array.isArray(readiness.blockers)) cards.push(["Blockers", String(readiness.blockers.length)]);
  if (typeof plan.ready_to_apply === "boolean") cards.push(["Ready to apply", plan.ready_to_apply ? "Yes" : "No"]);
  if (payload.patch_id) cards.push(["Patch ID", payload.patch_id]);
  if (payload.resolution_id) cards.push(["Resolution ID", payload.resolution_id]);
  if (payload.coordinate_plan_id) cards.push(["Coordinate plan ID", payload.coordinate_plan_id]);
  if (typeof payload.ready_for_executor === "boolean") {
    cards.push(["Ready for executor", payload.ready_for_executor ? "Yes" : "No"]);
  }
  if (typeof payload.execution_supported_by_this_release === "boolean") {
    cards.push(["Execution included", payload.execution_supported_by_this_release ? "Yes" : "No"]);
  }
  if (Array.isArray(payload.blockers)) cards.push(["Contract blockers", String(payload.blockers.length)]);
  if (Array.isArray(payload.resolutions)) {
    const blocked = payload.resolutions.filter((item) => item.status === "blocked").length;
    cards.push(["Target resolutions", String(payload.resolutions.length)]);
    cards.push(["Blocked targets", String(blocked)]);
  }
  if (Array.isArray(payload.operation_plans)) {
    const allocations = payload.operation_plans.reduce(
      (total, item) => total + (Array.isArray(item.allocations) ? item.allocations.length : 0),
      0,
    );
    cards.push(["Coordinate operations", String(payload.operation_plans.length)]);
    cards.push(["Planned ranges", String(allocations)]);
  }
  if (Array.isArray(plan.operations)) cards.push(["Operations", String(plan.operations.length)]);
  if (source.filename) cards.push(["Workbook", source.filename]);
  if (typeof workbook.sheet_count === "number") cards.push(["Sheets", String(workbook.sheet_count)]);
  if (Array.isArray(evidence.items)) cards.push(["Derived evidence", String(evidence.items.length)]);
  if (typeof payload.valid === "boolean") cards.push(["Valid", payload.valid ? "Yes" : "No"]);

  summary.replaceChildren();
  if (!cards.length) {
    summary.className = "summary empty";
    summary.textContent = "No summary fields available.";
    return;
  }
  summary.className = "summary";
  cards.forEach(([label, value]) => addSummaryCard(label, String(value)));
}

function showResult(kind, payload) {
  currentResult = payload;
  resultKind.textContent = kind;
  output.textContent = pretty(payload);
  copyButton.disabled = false;
  renderSummary(payload);
}

async function requestJson(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload.detail;
    const message = typeof detail === "string"
      ? detail
      : detail?.message || payload.error || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

async function run(path, label) {
  setStatus();
  try {
    const payload = parseEditor();
    const result = await requestJson(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    showResult(label, result);
  } catch (error) {
    setStatus(error.message);
  }
}

async function inspectWorkbook() {
  workbookStatus.textContent = "";
  const file = workbookFile.files[0];
  if (!file) {
    workbookStatus.textContent = "Select an .xlsx workbook.";
    return;
  }
  try {
    const result = await requestJson(
      `/api/v1/workbooks/inspect?filename=${encodeURIComponent(file.name)}`,
      {
        method: "POST",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
      },
    );
    currentWorkbookMap = result;
    invalidateAnalysis();
    analyseButton.disabled = false;
    showResult("Workbook map", result);
  } catch (error) {
    currentWorkbookMap = null;
    invalidateAnalysis();
    analyseButton.disabled = true;
    workbookStatus.textContent = error.message;
  }
}

async function analyseWorkbook() {
  workbookStatus.textContent = "";
  if (!currentWorkbookMap) {
    workbookStatus.textContent = "Inspect a workbook first.";
    return;
  }
  try {
    const result = await requestJson("/api/v1/workbooks/analyse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contract_version: "workbook-analysis-request.v1",
        workbook_map: currentWorkbookMap,
        model_request: parseEditor(),
      }),
    });
    currentAnalysis = result;
    currentPatch = null;
    currentTargetResolution = null;
    currentCoordinatePlan = null;
    compilePatchButton.disabled = false;
    resolveTargetsButton.disabled = true;
    planCoordinatesButton.disabled = true;
    showResult("Workbook analysis", result);
  } catch (error) {
    invalidateAnalysis();
    workbookStatus.textContent = error.message;
  }
}

async function compilePatch() {
  workbookStatus.textContent = "";
  if (!currentAnalysis) {
    workbookStatus.textContent = "Analyse the current workbook and request first.";
    return;
  }
  try {
    const result = await requestJson("/api/v1/workbooks/patches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentAnalysis),
    });
    currentPatch = result;
    currentTargetResolution = null;
    currentCoordinatePlan = null;
    resolveTargetsButton.disabled = false;
    planCoordinatesButton.disabled = true;
    showResult("Workbook patch manifest", result);
  } catch (error) {
    currentPatch = null;
    currentTargetResolution = null;
    currentCoordinatePlan = null;
    resolveTargetsButton.disabled = true;
    planCoordinatesButton.disabled = true;
    workbookStatus.textContent = error.message;
  }
}

async function resolveTargets() {
  workbookStatus.textContent = "";
  if (!currentAnalysis || !currentPatch) {
    workbookStatus.textContent = "Analyse the workbook and compile its patch first.";
    return;
  }
  try {
    const result = await requestJson("/api/v1/workbooks/target-resolutions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contract_version: "workbook-target-resolution-request.v1",
        workbook_analysis: currentAnalysis,
        workbook_patch: currentPatch,
      }),
    });
    currentTargetResolution = result;
    currentCoordinatePlan = null;
    planCoordinatesButton.disabled = false;
    showResult("Semantic target resolution", result);
  } catch (error) {
    currentTargetResolution = null;
    currentCoordinatePlan = null;
    planCoordinatesButton.disabled = true;
    workbookStatus.textContent = error.message;
  }
}

async function planCoordinates() {
  workbookStatus.textContent = "";
  if (!currentAnalysis || !currentPatch || !currentTargetResolution) {
    workbookStatus.textContent = "Resolve targets before planning coordinates.";
    return;
  }
  try {
    const count = parseForecastPeriodCount();
    const result = await requestJson("/api/v1/workbooks/coordinate-plans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contract_version: "workbook-coordinate-plan-request.v1",
        analysis: currentAnalysis,
        patch: currentPatch,
        target_resolution: currentTargetResolution,
        layout_parameters: { forecast_period_count: count },
      }),
    });
    currentCoordinatePlan = result;
    showResult("Workbook coordinate plan", result);
  } catch (error) {
    currentCoordinatePlan = null;
    workbookStatus.textContent = error.message;
  }
}

async function loadFixture(fixtureId) {
  const fixture = await requestJson(`/api/v1/fixtures/${encodeURIComponent(fixtureId)}`);
  currentFixture = fixture;
  editor.value = pretty(fixture);
  invalidateAnalysis();
  setStatus();
}

async function initialize() {
  try {
    const health = await requestJson("/health");
    healthIndicator.textContent = `${health.service} ${health.version} — local service ready`;
    healthIndicator.className = "health-ok";
  } catch (error) {
    healthIndicator.textContent = `Local service unavailable: ${error.message}`;
    healthIndicator.className = "health-error";
  }

  try {
    const fixtures = await requestJson("/api/v1/fixtures");
    fixtureSelect.replaceChildren();
    fixtures.forEach((fixture) => {
      const option = document.createElement("option");
      option.value = fixture.fixture_id;
      option.textContent = fixture.title;
      fixtureSelect.append(option);
    });
    if (fixtures.length) await loadFixture(fixtures[0].fixture_id);
  } catch (error) {
    setStatus(error.message);
  }
}

document.querySelector("#inspect-button").addEventListener("click", inspectWorkbook);
workbookFile.addEventListener("change", () => {
  currentWorkbookMap = null;
  invalidateAnalysis();
  analyseButton.disabled = true;
  workbookStatus.textContent = "";
});
editor.addEventListener("input", invalidateAnalysis);
forecastPeriodCount.addEventListener("input", invalidateCoordinatePlan);
analyseButton.addEventListener("click", analyseWorkbook);
compilePatchButton.addEventListener("click", compilePatch);
resolveTargetsButton.addEventListener("click", resolveTargets);
planCoordinatesButton.addEventListener("click", planCoordinates);
document.querySelector("#route-button").addEventListener("click", () => run("/api/v1/route", "Routing result"));
document.querySelector("#plan-button").addEventListener("click", () => run("/api/v1/plan", "Transformation plan"));
document.querySelector("#validate-button").addEventListener("click", async () => {
  setStatus();
  try {
    let path = "/api/v1/validate-plan";
    let label = "Plan validation";
    let payload = currentResult?.transformation_plan || currentResult;
    if (currentResult?.contract_version === "workbook-coordinate-plan.v1") {
      path = "/api/v1/workbooks/coordinate-plans/validate";
      label = "Coordinate plan validation";
      payload = {
        coordinate_plan: currentResult,
        analysis: currentAnalysis,
        patch: currentPatch,
        target_resolution: currentTargetResolution,
        layout_parameters: {
          forecast_period_count: parseForecastPeriodCount(),
        },
      };
    } else if (currentResult?.contract_version === "workbook-target-resolution.v1") {
      path = "/api/v1/workbooks/target-resolutions/validate";
      label = "Target resolution validation";
      payload = {
        target_resolution: currentResult,
        workbook_analysis: currentAnalysis,
        workbook_patch: currentPatch,
      };
    } else if (currentResult?.contract_version === "workbook-patch.v1") {
      path = "/api/v1/workbooks/patches/validate";
      label = "Patch validation";
      payload = currentResult;
    } else if (payload?.contract_version !== "transformation-plan.v1") {
      payload = parseEditor();
    }
    const result = await requestJson(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    showResult(label, result);
  } catch (error) {
    setStatus(error.message);
  }
});
document.querySelector("#reset-button").addEventListener("click", () => {
  if (currentFixture) editor.value = pretty(currentFixture);
  invalidateAnalysis();
  setStatus();
});
fixtureSelect.addEventListener("change", () => loadFixture(fixtureSelect.value));
copyButton.addEventListener("click", async () => {
  if (!currentResult) return;
  await navigator.clipboard.writeText(pretty(currentResult));
  copyButton.textContent = "Copied";
  setTimeout(() => { copyButton.textContent = "Copy JSON"; }, 1200);
});

initialize();
