const financialDataFile = document.querySelector("#financial-data-file");
const importFinancialDataButton = document.querySelector("#import-financial-data-button");
const mapFinancialDataButton = document.querySelector("#map-financial-data-button");
const planFinancialBindingsButton = document.querySelector("#plan-financial-bindings-button");
const compileFinancialInputSetButton = document.querySelector("#compile-financial-input-set-button");
const financialMappingRulesEditor = document.querySelector("#financial-mapping-rules-editor");
const financialBindingProfileEditor = document.querySelector("#financial-binding-profile-editor");
const financialDataStatus = document.querySelector("#financial-data-status");

let currentFinancialDataPackage = null;
let currentFinancialMappingProfile = null;
let currentFinancialMappingResult = null;
let currentFinancialBindingProfile = null;
let currentFinancialBindingPlan = null;

function parseArrayEditor(editor, label) {
  const value = JSON.parse(editor.value || "[]");
  if (!Array.isArray(value) || value.some((item) => !item || typeof item !== "object" || Array.isArray(item))) {
    throw new Error(`${label} must be a JSON array of objects.`);
  }
  return value;
}

function invalidateFinancialMapping() {
  currentFinancialMappingProfile = null;
  currentFinancialMappingResult = null;
  currentFinancialBindingProfile = null;
  currentFinancialBindingPlan = null;
  refreshFinancialDataButtons();
}

function invalidateFinancialBinding() {
  currentFinancialBindingProfile = null;
  currentFinancialBindingPlan = null;
  refreshFinancialDataButtons();
}

function refreshFinancialDataButtons() {
  importFinancialDataButton.disabled = !financialDataFile.files[0];
  mapFinancialDataButton.disabled = !currentFinancialDataPackage;
  planFinancialBindingsButton.disabled = !(
    currentFinancialDataPackage
    && currentFinancialMappingResult
    && currentWritePlan
    && currentExecutionReceipt
  );
  compileFinancialInputSetButton.disabled = !(
    currentFinancialBindingPlan
    && currentFinancialBindingPlan.ready_for_input_set
    && currentWritePlan
    && currentExecutionReceipt
  );
}

async function importFinancialData() {
  financialDataStatus.textContent = "";
  const file = financialDataFile.files[0];
  if (!file) return;
  importFinancialDataButton.disabled = true;
  try {
    currentFinancialDataPackage = await requestJson("/api/v1/financial-data/packages/from-csv", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contract_version: "financial-data-csv-request.v1",
        source_name: file.name,
        csv_base64: await fileToBase64(file),
      }),
    });
    invalidateFinancialMapping();
    financialDataStatus.textContent = `Imported ${currentFinancialDataPackage.rows.length} account rows across ${currentFinancialDataPackage.periods.length} periods.`;
    showResult("Financial data package", currentFinancialDataPackage);
  } catch (error) {
    currentFinancialDataPackage = null;
    invalidateFinancialMapping();
    financialDataStatus.textContent = error.message;
  } finally {
    refreshFinancialDataButtons();
  }
}

async function mapFinancialData() {
  financialDataStatus.textContent = "";
  if (!currentFinancialDataPackage) return;
  mapFinancialDataButton.disabled = true;
  try {
    const rules = parseArrayEditor(financialMappingRulesEditor, "Mapping rules");
    currentFinancialMappingProfile = await requestJson("/api/v1/financial-data/mapping-profiles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "workbench mapping profile", rules }),
    });
    currentFinancialMappingResult = await requestJson("/api/v1/financial-data/mappings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        package: currentFinancialDataPackage,
        profile: currentFinancialMappingProfile,
      }),
    });
    currentFinancialBindingProfile = null;
    currentFinancialBindingPlan = null;
    const unresolved = currentFinancialMappingResult.row_mappings.filter((item) => item.status !== "mapped").length;
    financialDataStatus.textContent = `${currentFinancialMappingResult.concept_series.length} concept-period values mapped; ${unresolved} source rows need review.`;
    showResult("Financial data mapping", currentFinancialMappingResult);
  } catch (error) {
    currentFinancialMappingProfile = null;
    currentFinancialMappingResult = null;
    currentFinancialBindingPlan = null;
    financialDataStatus.textContent = error.message;
  } finally {
    refreshFinancialDataButtons();
  }
}

async function planFinancialBindings() {
  financialDataStatus.textContent = "";
  if (!currentFinancialDataPackage || !currentFinancialMappingResult || !currentWritePlan || !currentExecutionReceipt) return;
  planFinancialBindingsButton.disabled = true;
  try {
    const bindings = parseArrayEditor(financialBindingProfileEditor, "Semantic slot bindings");
    currentFinancialBindingProfile = await requestJson("/api/v1/financial-data/binding-profiles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "workbench binding profile", bindings }),
    });
    currentFinancialBindingPlan = await requestJson("/api/v1/financial-data/binding-plans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        package: currentFinancialDataPackage,
        mapping_result: currentFinancialMappingResult,
        binding_profile: currentFinancialBindingProfile,
        write_plan: currentWritePlan,
        execution_receipt: currentExecutionReceipt,
      }),
    });
    financialDataStatus.textContent = currentFinancialBindingPlan.ready_for_input_set
      ? `All ${currentFinancialBindingPlan.bound_records.length} reserved input records are bound.`
      : `${currentFinancialBindingPlan.bound_records.length} records bound; ${currentFinancialBindingPlan.unresolved_records.length} unresolved.`;
    showResult("Financial input binding plan", currentFinancialBindingPlan);
  } catch (error) {
    currentFinancialBindingProfile = null;
    currentFinancialBindingPlan = null;
    financialDataStatus.textContent = error.message;
  } finally {
    refreshFinancialDataButtons();
  }
}

async function compileFinancialInputSet() {
  financialDataStatus.textContent = "";
  if (!currentFinancialBindingPlan || !currentWritePlan || !currentExecutionReceipt) return;
  compileFinancialInputSetButton.disabled = true;
  try {
    const inputSet = await requestJson("/api/v1/financial-data/input-sets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        binding_plan: currentFinancialBindingPlan,
        write_plan: currentWritePlan,
        execution_receipt: currentExecutionReceipt,
      }),
    });
    currentInputSet = inputSet;
    inputSetEditor.value = JSON.stringify(inputSet, null, 2);
    financialDataStatus.textContent = "Ready financial binding plan compiled into workbook-input-set.v1.";
    showResult("Governed workbook input set", inputSet);
    refreshInputPopulationButtons();
  } catch (error) {
    financialDataStatus.textContent = error.message;
  } finally {
    refreshFinancialDataButtons();
  }
}

financialDataFile.addEventListener("change", () => {
  currentFinancialDataPackage = null;
  invalidateFinancialMapping();
});
financialMappingRulesEditor.addEventListener("input", invalidateFinancialMapping);
financialBindingProfileEditor.addEventListener("input", invalidateFinancialBinding);
importFinancialDataButton.addEventListener("click", importFinancialData);
mapFinancialDataButton.addEventListener("click", mapFinancialData);
planFinancialBindingsButton.addEventListener("click", planFinancialBindings);
compileFinancialInputSetButton.addEventListener("click", compileFinancialInputSet);

for (const target of [workbookFile, editor, forecastPeriodCount, writeContextEditor, fixtureSelect]) {
  target.addEventListener(
    target === editor || target === forecastPeriodCount || target === writeContextEditor ? "input" : "change",
    () => {
      currentFinancialBindingPlan = null;
      refreshFinancialDataButtons();
    },
  );
}
for (const button of [
  analyseButton,
  compilePatchButton,
  resolveTargetsButton,
  planCoordinatesButton,
  planContentButton,
  planRealizationButton,
  planWritesButton,
  executeWorkbookButton,
  document.querySelector("#reset-button"),
]) {
  button.addEventListener("click", () => {
    currentFinancialBindingPlan = null;
    refreshFinancialDataButtons();
  });
}

refreshFinancialDataButtons();
