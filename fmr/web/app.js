const editor = document.querySelector("#request-editor");
const fixtureSelect = document.querySelector("#fixture-select");
const output = document.querySelector("#result-output");
const summary = document.querySelector("#summary");
const resultKind = document.querySelector("#result-kind");
const requestStatus = document.querySelector("#request-status");
const workbookStatus = document.querySelector("#workbook-status");
const workbookFile = document.querySelector("#workbook-file");
const analyseButton = document.querySelector("#analyse-button");
const copyButton = document.querySelector("#copy-button");
const healthIndicator = document.querySelector("#health-indicator");

let currentFixture = null;
let currentResult = null;
let currentWorkbookMap = null;

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

function setStatus(message = "") {
  requestStatus.textContent = message;
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
    analyseButton.disabled = false;
    showResult("Workbook map", result);
  } catch (error) {
    currentWorkbookMap = null;
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
    showResult("Workbook analysis", result);
  } catch (error) {
    workbookStatus.textContent = error.message;
  }
}

async function loadFixture(fixtureId) {
  const fixture = await requestJson(`/api/v1/fixtures/${encodeURIComponent(fixtureId)}`);
  currentFixture = fixture;
  editor.value = pretty(fixture);
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
analyseButton.addEventListener("click", analyseWorkbook);
document.querySelector("#route-button").addEventListener("click", () => run("/api/v1/route", "Routing result"));
document.querySelector("#plan-button").addEventListener("click", () => run("/api/v1/plan", "Transformation plan"));
document.querySelector("#validate-button").addEventListener("click", async () => {
  setStatus();
  try {
    const candidate = currentResult?.transformation_plan || currentResult;
    const payload = candidate?.contract_version === "transformation-plan.v1"
      ? candidate
      : parseEditor();
    const result = await requestJson("/api/v1/validate-plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    showResult("Plan validation", result);
  } catch (error) {
    setStatus(error.message);
  }
});
document.querySelector("#reset-button").addEventListener("click", () => {
  if (currentFixture) editor.value = pretty(currentFixture);
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
