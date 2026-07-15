const scopeObjective = document.querySelector("#scope-objective");
const scopeDecision = document.querySelector("#scope-decision");
const scopeFormat = document.querySelector("#scope-format");
const scopeQuestions = document.querySelector("#scope-questions");
const scopeCandidates = document.querySelector("#scope-candidates");
const scopeStatus = document.querySelector("#scope-status");
const answerScopeButton = document.querySelector("#answer-scope-button");
const confirmScopeButton = document.querySelector("#confirm-scope-button");
const compileScopedJobButton = document.querySelector("#compile-scoped-job-button");

let scopeKnowledge = null;
let currentScopeIntent = null;
let currentScopeAssessment = null;
let currentScopeConfirmation = null;

function resetScopeProgress() {
  currentScopeAssessment = null;
  currentScopeConfirmation = null;
  scopeQuestions.replaceChildren();
  scopeCandidates.replaceChildren();
  answerScopeButton.disabled = true;
  confirmScopeButton.disabled = true;
  compileScopedJobButton.disabled = true;
}

function fieldset(title) {
  const element = document.createElement("fieldset");
  const legend = document.createElement("legend");
  legend.textContent = title;
  element.append(legend);
  return element;
}

async function knowledge() {
  if (!scopeKnowledge) scopeKnowledge = await requestJson("/api/v2/scoping/knowledge");
  return scopeKnowledge;
}

function renderScopeQuestions(assessment, registry) {
  scopeQuestions.replaceChildren();
  assessment.clarification_questions.forEach((prompt) => {
    const question = registry.questions.find((item) => item.prompt === prompt);
    if (!question) return;
    const wrapper = fieldset(prompt);
    const select = document.createElement("select");
    select.dataset.questionId = question.question_id;
    question.options.forEach((option) => {
      const node = document.createElement("option");
      node.value = option.value;
      node.textContent = option.label;
      select.append(node);
    });
    wrapper.append(select);
    scopeQuestions.append(wrapper);
  });
  answerScopeButton.disabled = scopeQuestions.querySelectorAll("select").length === 0;
}

function renderScopeCandidates(assessment) {
  scopeCandidates.replaceChildren();
  assessment.candidates.forEach((candidate) => {
    const wrapper = fieldset(candidate.title);
    const selection = document.createElement("input");
    selection.type = "radio";
    selection.name = "scope-candidate";
    selection.value = candidate.family_id;
    selection.disabled = !["eligible", "possible"].includes(candidate.suitability);
    const status = document.createElement("strong");
    status.textContent = ` ${candidate.suitability}`;
    wrapper.append(selection, status);
    const purpose = document.createElement("p");
    purpose.textContent = candidate.purpose;
    wrapper.append(purpose);
    const missing = document.createElement("p");
    missing.textContent = candidate.missing_information.length
      ? `Missing: ${candidate.missing_information.join(", ")}`
      : "Required inputs are declared available.";
    wrapper.append(missing);
    candidate.limitations.forEach((limitation) => {
      const label = document.createElement("label");
      const acknowledgement = document.createElement("input");
      acknowledgement.type = "checkbox";
      acknowledgement.dataset.family = candidate.family_id;
      acknowledgement.value = limitation;
      label.append(acknowledgement, document.createTextNode(` I understand: ${limitation}`));
      wrapper.append(label);
    });
    scopeCandidates.append(wrapper);
  });
  confirmScopeButton.disabled = !assessment.candidates.some((item) => ["eligible", "possible"].includes(item.suitability));
}

async function assessScope() {
  scopeStatus.textContent = "";
  resetScopeProgress();
  try {
    currentScopeIntent = await requestJson("/api/v2/scoping/intents", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        objective: scopeObjective.value,
        decision_context: scopeDecision.value,
        requested_outcomes: [scopeObjective.value],
        output_formats: [scopeFormat.value],
      }),
    });
    if (currentWorkbookMap) {
      const evidence = await requestJson("/api/v2/scoping/workbook-evidence", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({workbook_map: currentWorkbookMap}),
      });
      currentScopeIntent = await requestJson("/api/v2/scoping/workbook-intents", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({intent: currentScopeIntent, evidence, workbook_map: currentWorkbookMap}),
      });
    }
    currentScopeAssessment = await requestJson("/api/v2/scoping/assessments", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(currentScopeIntent),
    });
    const registry = await knowledge();
    renderScopeQuestions(currentScopeAssessment, registry);
    renderScopeCandidates(currentScopeAssessment);
    showResult("Model scope assessment", currentScopeAssessment);
  } catch (error) {
    scopeStatus.textContent = error.message;
  }
}

async function applyScopeAnswers() {
  scopeStatus.textContent = "";
  try {
    for (const select of scopeQuestions.querySelectorAll("select")) {
      currentScopeIntent = await requestJson("/api/v2/scoping/answers", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({intent: currentScopeIntent, question_id: select.dataset.questionId, answer: select.value}),
      });
    }
    currentScopeAssessment = await requestJson("/api/v2/scoping/assessments", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(currentScopeIntent),
    });
    renderScopeQuestions(currentScopeAssessment, await knowledge());
    renderScopeCandidates(currentScopeAssessment);
    showResult("Updated model scope assessment", currentScopeAssessment);
  } catch (error) {
    scopeStatus.textContent = error.message;
  }
}

async function confirmScope() {
  scopeStatus.textContent = "";
  try {
    const selected = scopeCandidates.querySelector('input[name="scope-candidate"]:checked');
    if (!selected) throw new Error("Select a model scope first.");
    const limitations = [...scopeCandidates.querySelectorAll(`input[type="checkbox"][data-family="${selected.value}"]`)];
    if (limitations.some((item) => !item.checked)) throw new Error("Acknowledge every limitation for the selected scope.");
    currentScopeConfirmation = await requestJson("/api/v2/scoping/confirmations", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({assessment: currentScopeAssessment, selected_family: selected.value, acknowledged_limitations: limitations.map((item) => item.value)}),
    });
    compileScopedJobButton.disabled = false;
    showResult("Scope confirmation", currentScopeConfirmation);
  } catch (error) {
    scopeStatus.textContent = error.message;
  }
}

async function compileScopedJob() {
  scopeStatus.textContent = "";
  try {
    const job = await requestJson("/api/v2/scoping/jobs", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({assessment: currentScopeAssessment, confirmation: currentScopeConfirmation}),
    });
    providerJobEditor.value = JSON.stringify(job, null, 2);
    showResult("Confirmed provider-neutral model job", job);
    scopeStatus.textContent = "The confirmed job is ready for provider routing below.";
  } catch (error) {
    scopeStatus.textContent = error.message;
  }
}

document.querySelector("#assess-scope-button").addEventListener("click", assessScope);
answerScopeButton.addEventListener("click", applyScopeAnswers);
confirmScopeButton.addEventListener("click", confirmScope);
compileScopedJobButton.addEventListener("click", compileScopedJob);
