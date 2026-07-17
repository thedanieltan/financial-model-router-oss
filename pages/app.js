const cases = {
  monthly_forecast: {
    title: "Monthly forecast update",
    role: "FP&A",
    description: "Route and run a rolling forecast using three years of synthetic actuals.",
    fields: [
      ["forecast_horizon", "Forecast years", "number", 3, 1, 10],
      ["revenue_growth_rate", "Revenue growth", "number", 0.08, -0.9, 2, 0.01],
      ["operating_cost_growth_rate", "Operating-cost growth", "number", 0.05, -0.9, 2, 0.01],
      ["scenario", "Scenario", "select", "base", ["base", "upside", "downside"]],
    ],
  },
  operating_valuation: {
    title: "Operating-company DCF",
    role: "Private equity",
    description: "Route and run the deterministic Python Forecast DCF package.",
    fields: [
      ["forecast_horizon", "Forecast years", "number", 5, 1, 10],
      ["revenue_growth_rate", "Revenue growth", "number", 0.08, -0.9, 2, 0.01],
      ["operating_margin_rate", "Operating margin", "number", 0.2, 0, 1, 0.01],
      ["discount_rate", "Discount rate", "number", 0.1, 0.001, 1, 0.01],
      ["terminal_growth_rate", "Terminal growth", "number", 0.02, -0.5, 0.5, 0.01],
      ["net_debt", "Net debt (SGD)", "number", 300000, 0, 100000000, 1000],
    ],
  },
  debt_capacity: {
    title: "Debt-capacity refresh",
    role: "Finance manager",
    description: "Route and run leverage, debt-service and covenant calculations.",
    fields: [
      ["forecast_horizon", "Forecast years", "number", 4, 1, 10],
      ["opening_debt", "Opening debt (SGD)", "number", 300000, 0, 100000000, 1000],
      ["annual_repayment", "Annual repayment (SGD)", "number", 75000, 0, 100000000, 1000],
      ["interest_rate_assumption", "Interest rate", "number", 0.05, 0, 2, 0.01],
      ["ebitda_growth_rate", "EBITDA growth", "number", 0.05, -0.9, 2, 0.01],
      ["maximum_leverage_ratio", "Maximum leverage", "number", 3, 0, 20, 0.1],
      ["minimum_debt_service_coverage", "Minimum DSCR", "number", 1.5, 0, 20, 0.1],
    ],
  },
  project_finance: {
    title: "Project-finance debt sculpting",
    role: "Project finance",
    description: "Demonstrate honest blocking where no conformant provider package exists.",
    fields: [],
  },
};

const state = { worker: null, ready: false, pending: new Map(), requestId: 0 };
const caseSelect = document.querySelector("#case-select");
const fields = document.querySelector("#assumption-fields");
const runtimeStatus = document.querySelector("#runtime-status");
const compileButton = document.querySelector("#compile-button");
const executeButton = document.querySelector("#execute-button");
const output = document.querySelector("#output");
const resultTitle = document.querySelector("#result-title");

function setRuntime(message, tone = "neutral") {
  runtimeStatus.textContent = message;
  runtimeStatus.dataset.tone = tone;
}

function renderCase() {
  const config = cases[caseSelect.value];
  document.querySelector("#case-title").textContent = config.title;
  document.querySelector("#case-role").textContent = config.role;
  document.querySelector("#case-description").textContent = config.description;
  fields.replaceChildren();
  for (const [key, label, type, value, fourth, fifth, sixth] of config.fields) {
    const wrapper = document.createElement("label");
    wrapper.className = "field";
    const span = document.createElement("span");
    span.textContent = label;
    let input;
    if (type === "select") {
      input = document.createElement("select");
      for (const optionValue of fourth) {
        const option = document.createElement("option");
        option.value = optionValue;
        option.textContent = optionValue[0].toUpperCase() + optionValue.slice(1);
        option.selected = optionValue === value;
        input.append(option);
      }
    } else {
      input = document.createElement("input");
      input.type = type;
      input.value = value;
      input.min = fourth;
      input.max = fifth;
      input.step = sixth || "any";
    }
    input.dataset.assumption = key;
    wrapper.append(span, input);
    fields.append(wrapper);
  }
  output.replaceChildren();
  output.className = "output-empty";
  const empty = document.createElement("p");
  empty.textContent = "The compiled blueprint, provider selection, blockers, execution state and model artifact will appear here.";
  output.append(empty);
  resultTitle.textContent = "No result yet";
  executeButton.disabled = !state.ready || caseSelect.value === "project_finance";
}

function assumptions() {
  const result = {};
  document.querySelectorAll("[data-assumption]").forEach((input) => {
    if (input.type === "number") {
      result[input.dataset.assumption] = input.dataset.assumption === "forecast_horizon"
        ? Number.parseInt(input.value, 10)
        : String(input.value);
    } else {
      result[input.dataset.assumption] = input.value;
    }
  });
  if (caseSelect.value === "monthly_forecast") {
    const scenario = result.scenario || "base";
    result.scenario_adjustments = {
      [scenario]: { revenue_growth_delta: "0", operating_cost_growth_delta: "0" },
    };
  }
  return result;
}

function callWorker(action) {
  const id = ++state.requestId;
  return new Promise((resolve, reject) => {
    state.pending.set(id, { resolve, reject });
    state.worker.postMessage({ id, action, payload: { case_id: caseSelect.value, assumptions: assumptions() } });
  });
}

function badge(text, tone = "neutral") {
  const element = document.createElement("span");
  element.className = `badge badge-${tone}`;
  element.textContent = text;
  return element;
}

function renderResult(result) {
  output.replaceChildren();
  output.className = "";
  const plan = result.plan;
  resultTitle.textContent = `${cases[result.case_id].title} · ${plan.status.replaceAll("_", " ")}`;

  const summary = document.createElement("section");
  summary.className = "result-card";
  const heading = document.createElement("h3");
  heading.textContent = "Routing result";
  const badges = document.createElement("div");
  badges.className = "badges";
  badges.append(
    badge(plan.blueprint.blueprint_id, "accent"),
    badge(plan.status, plan.status === "blocked" ? "danger" : "success"),
    badge("synthetic data"),
    badge("not production accepted", "warning"),
  );
  summary.append(heading, badges);
  output.append(summary);

  const steps = document.createElement("section");
  steps.className = "result-card";
  const stepHeading = document.createElement("h3");
  stepHeading.textContent = "Workflow steps";
  steps.append(stepHeading);
  const list = document.createElement("ol");
  list.className = "steps";
  for (const step of plan.steps) {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = step.step_id.replaceAll("_", " ");
    const detail = document.createElement("span");
    const provider = step.provider_id ? ` · ${step.provider_id}/${step.package_id}` : "";
    const blockers = step.blockers.length ? ` · ${step.blockers.join(", ")}` : "";
    detail.textContent = `${step.status}${provider}${blockers}`;
    item.append(title, detail);
    list.append(item);
  }
  steps.append(list);
  output.append(steps);

  if (result.execution) {
    const execution = document.createElement("section");
    execution.className = "result-card";
    const executionHeading = document.createElement("h3");
    executionHeading.textContent = "Execution";
    execution.append(executionHeading, badge(result.execution.state, result.execution.state === "completed" ? "success" : "warning"));
    output.append(execution);
  }

  if (result.artifact) renderArtifact(result.artifact);
}

function renderArtifact(artifact) {
  const card = document.createElement("section");
  card.className = "result-card";
  const heading = document.createElement("h3");
  heading.textContent = "Model output";
  card.append(heading);

  const headline = document.createElement("div");
  headline.className = "headline-values";
  for (const key of ["enterprise_value", "equity_value", "all_covenants_pass", "scenario"]) {
    if (!(key in artifact)) continue;
    const metric = document.createElement("div");
    const label = document.createElement("span");
    label.textContent = key.replaceAll("_", " ");
    const value = document.createElement("strong");
    value.textContent = String(artifact[key]);
    metric.append(label, value);
    headline.append(metric);
  }
  if (headline.children.length) card.append(headline);

  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(Array.isArray(artifact.forecast) ? artifact.forecast : artifact, null, 2);
  card.append(pre);
  output.append(card);
}

async function run(action) {
  compileButton.disabled = true;
  executeButton.disabled = true;
  setRuntime(action === "execute" ? "Running the selected FMR provider in your browser…" : "Compiling the workflow with the FMR router…", "busy");
  try {
    renderResult(await callWorker(action));
    setRuntime("FMR browser runtime ready. No case data was sent to a server.", "success");
  } catch (error) {
    setRuntime(error.message, "danger");
  } finally {
    compileButton.disabled = !state.ready;
    executeButton.disabled = !state.ready || caseSelect.value === "project_finance";
  }
}

function startWorker() {
  state.worker = new Worker("worker.js");
  state.worker.onmessage = (event) => {
    const message = event.data || {};
    if (message.type === "ready") {
      state.ready = true;
      setRuntime("FMR browser runtime ready. No case data is sent to a server.", "success");
      compileButton.disabled = false;
      executeButton.disabled = caseSelect.value === "project_finance";
      return;
    }
    if (message.type === "fatal") {
      setRuntime(`The browser runtime could not start: ${message.error}`, "danger");
      return;
    }
    const pending = state.pending.get(message.id);
    if (!pending) return;
    state.pending.delete(message.id);
    if (message.type === "result") pending.resolve(message.result);
    else pending.reject(new Error(message.error || "The browser worker failed."));
  };
}

caseSelect.addEventListener("change", renderCase);
compileButton.addEventListener("click", () => run("compile"));
executeButton.addEventListener("click", () => run("execute"));
renderCase();
startWorker();
