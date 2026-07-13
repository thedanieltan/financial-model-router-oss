const planWritesButton = document.querySelector("#plan-writes-button");
const writeContextEditor = document.querySelector("#write-context-editor");
let currentWritePlan = null;

function baseWriteContext() {
  return {
    contract_version: "workbook-write-context.v1",
    period_labels: [
      "P1", "P2", "P3", "P4", "P5", "P6",
      "P7", "P8", "P9", "P10", "P11", "P12",
    ],
    bindings: {},
  };
}

function parseWriteContext() {
  const value = JSON.parse(writeContextEditor.value);
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new Error("Write context JSON root must be an object.");
  }
  return value;
}

function visibleSyntheticContext(realizationPlan) {
  const context = baseWriteContext();
  for (const operation of realizationPlan.operation_realizations || []) {
    for (const slot of operation.slots || []) {
      const formula = slot.formula_binding;
      if (!formula) continue;
      for (const dependency of formula.dependencies || []) {
        if (["content_slot", "period_context"].includes(dependency.binding_type)) continue;
        context.bindings[dependency.identifier] = {
          binding_type: "constant",
          value: dependency.binding_type === "validation_context" ? true : 1,
        };
      }
    }
  }
  return context;
}

function invalidateWritePlan() {
  currentWritePlan = null;
  planWritesButton.disabled = true;
}

async function planWrites() {
  workbookStatus.textContent = "";
  if (!currentRealizationPlan) {
    workbookStatus.textContent = "Plan formulas and styles before planning dry-run writes.";
    return;
  }
  try {
    const context = parseWriteContext();
    const result = await requestJson("/api/v1/workbooks/write-plans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contract_version: "workbook-write-plan-request.v1",
        realization_plan: currentRealizationPlan,
        write_context: context,
      }),
    });
    currentWritePlan = result;
    showResult("Workbook dry-run write plan", result);
  } catch (error) {
    currentWritePlan = null;
    workbookStatus.textContent = error.message;
  }
}

writeContextEditor.value = pretty(baseWriteContext());
planWritesButton.addEventListener("click", planWrites);
writeContextEditor.addEventListener("input", () => {
  currentWritePlan = null;
});

const writePlanResultObserver = new MutationObserver(() => {
  if (currentResult?.contract_version === "workbook-realization-plan.v1" && currentRealizationPlan) {
    currentWritePlan = null;
    writeContextEditor.value = pretty(visibleSyntheticContext(currentRealizationPlan));
    planWritesButton.disabled = false;
    workbookStatus.textContent = "Synthetic write bindings were generated for local testing. Review them before planning writes.";
  }
});
writePlanResultObserver.observe(document.querySelector("#result-output"), {
  childList: true,
  characterData: true,
  subtree: true,
});

for (const target of [workbookFile, editor, forecastPeriodCount, fixtureSelect]) {
  target.addEventListener(target === editor || target === forecastPeriodCount ? "input" : "change", invalidateWritePlan);
}
for (const button of [
  analyseButton,
  compilePatchButton,
  resolveTargetsButton,
  planCoordinatesButton,
  planContentButton,
  planRealizationButton,
  document.querySelector("#reset-button"),
]) {
  button.addEventListener("click", invalidateWritePlan);
}

validateDisplayedButton.addEventListener("click", async (event) => {
  if (currentResult?.contract_version !== "workbook-write-plan.v1") return;
  event.preventDefault();
  event.stopImmediatePropagation();
  setStatus();
  try {
    const result = await requestJson("/api/v1/workbooks/write-plans/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        write_plan: currentResult,
        realization_plan: currentRealizationPlan,
        write_context: parseWriteContext(),
      }),
    });
    showResult("Write plan validation", result);
  } catch (error) {
    setStatus(error.message);
  }
}, true);
