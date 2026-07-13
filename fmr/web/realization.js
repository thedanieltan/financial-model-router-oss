const planRealizationButton = document.querySelector("#plan-realization-button");
const validateDisplayedButton = document.querySelector("#validate-button");
let currentRealizationPlan = null;

function invalidateRealizationPlan() {
  currentRealizationPlan = null;
  planRealizationButton.disabled = true;
}

async function planRealization() {
  workbookStatus.textContent = "";
  if (!currentContentPlan) {
    workbookStatus.textContent = "Plan content before planning formulas and styles.";
    return;
  }
  try {
    const result = await requestJson("/api/v1/workbooks/realization-plans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contract_version: "workbook-realization-plan-request.v1",
        content_plan: currentContentPlan,
      }),
    });
    currentRealizationPlan = result;
    showResult("Workbook formula and style realization plan", result);
  } catch (error) {
    currentRealizationPlan = null;
    workbookStatus.textContent = error.message;
  }
}

planRealizationButton.addEventListener("click", planRealization);

const resultObserver = new MutationObserver(() => {
  if (currentResult?.contract_version === "workbook-content-plan.v1" && currentContentPlan) {
    currentRealizationPlan = null;
    planRealizationButton.disabled = false;
  }
});
resultObserver.observe(document.querySelector("#result-output"), {
  childList: true,
  characterData: true,
  subtree: true,
});

for (const target of [
  workbookFile,
  editor,
  forecastPeriodCount,
  fixtureSelect,
]) {
  target.addEventListener(target === editor || target === forecastPeriodCount ? "input" : "change", invalidateRealizationPlan);
}

for (const button of [
  analyseButton,
  compilePatchButton,
  resolveTargetsButton,
  planCoordinatesButton,
  planContentButton,
  document.querySelector("#reset-button"),
]) {
  button.addEventListener("click", invalidateRealizationPlan);
}

validateDisplayedButton.addEventListener("click", async (event) => {
  if (currentResult?.contract_version !== "workbook-realization-plan.v1") return;
  event.preventDefault();
  event.stopImmediatePropagation();
  setStatus();
  try {
    const result = await requestJson("/api/v1/workbooks/realization-plans/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        realization_plan: currentResult,
        content_plan: currentContentPlan,
      }),
    });
    showResult("Realization plan validation", result);
  } catch (error) {
    setStatus(error.message);
  }
}, true);
