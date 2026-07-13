const editor = document.querySelector("#request-editor");
const fixtureSelect = document.querySelector("#fixture-select");
const output = document.querySelector("#result-output");
const summary = document.querySelector("#summary");
const resultKind = document.querySelector("#result-kind");
const requestStatus = document.querySelector("#request-status");
const copyButton = document.querySelector("#copy-button");
const healthIndicator = document.querySelector("#health-indicator");

let currentFixture = null;
let currentResult = null;

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

function renderSummary(payload) {
  const readiness = payload.readiness || {};
  const cards = [];
  if (payload.model_family) cards.push(["Model family", payload.model_family]);
  if (payload.title) cards.push(["Title", payload.title]);
  if (payload.confidence) cards.push(["Confidence", payload.confidence]);
  if (typeof readiness.ready === "boolean") cards.push(["Ready", readiness.ready ? "Yes" : "No"]);
  if (typeof payload.ready_to_apply === "boolean") cards.push(["Ready to apply", payload.ready_to_apply ? "Yes" : "No"]);
  if (Array.isArray(readiness.blockers)) cards.push(["Blockers", String(readiness.blockers.length)]);
  if (Array.isArray(payload.unresolved_inputs)) cards.push(["Unresolved inputs", String(payload.unresolved_inputs.length)]);
  if (Array.isArray(payload.operations)) cards.push(["Operations", String(payload.operations.length)]);
  if (typeof payload.valid === "boolean") cards.push(["Valid", payload.valid ? "Yes" : "No"]);

  if (!cards.length) {
    summary.className = "summary empty";
    summary.textContent = "No summary fields available.";
    return;
  }
  summary.className = "summary";
  summary.innerHTML = cards.map(([label, value]) => (
    `<div class="card"><span>${label}</span><strong>${value}</strong></div>`
  )).join("");
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
    fixtureSelect.innerHTML = fixtures.map((fixture) => (
      `<option value="${fixture.fixture_id}">${fixture.title}</option>`
    )).join("");
    if (fixtures.length) await loadFixture(fixtures[0].fixture_id);
  } catch (error) {
    setStatus(error.message);
  }
}

document.querySelector("#route-button").addEventListener("click", () => run("/api/v1/route", "Routing result"));
document.querySelector("#plan-button").addEventListener("click", () => run("/api/v1/plan", "Transformation plan"));
document.querySelector("#validate-button").addEventListener("click", async () => {
  setStatus();
  try {
    const payload = currentResult?.contract_version === "transformation-plan.v1"
      ? currentResult
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
