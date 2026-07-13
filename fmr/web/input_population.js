const inputCsvFile = document.querySelector("#input-csv-file");
const compileInputCsvButton = document.querySelector("#compile-input-csv-button");
const inputSetEditor = document.querySelector("#input-set-editor");
const populateInputsButton = document.querySelector("#populate-inputs-button");
const inputPopulationStatus = document.querySelector("#input-population-status");
let currentInputSet = null;
let currentInputPopulationReceipt = null;
let currentPopulatedWorkbookBase64 = null;
let currentPopulatedWorkbookFilename = null;

function populatedWorkbookName(filename) {
  return filename.replace(/\.xlsx$/i, "-populated.xlsx");
}

function invalidateInputPopulation() {
  currentInputSet = null;
  currentInputPopulationReceipt = null;
  currentPopulatedWorkbookBase64 = null;
  currentPopulatedWorkbookFilename = null;
  refreshInputPopulationButtons();
}

function parseInputSetEditor() {
  const text = inputSetEditor.value.trim();
  if (!text) return null;
  const payload = JSON.parse(text);
  if (!payload || payload.contract_version !== "workbook-input-set.v1") {
    throw new Error("Input-set JSON must use workbook-input-set.v1.");
  }
  return payload;
}

function refreshInputPopulationButtons() {
  compileInputCsvButton.disabled = !(
    inputCsvFile.files[0]
    && currentWritePlan
    && currentExecutionReceipt
  );
  populateInputsButton.disabled = !(
    inputSetEditor.value.trim()
    && currentExecutedWorkbookBase64
    && currentExecutedWorkbookFilename
    && currentWritePlan
    && currentExecutionReceipt
  );
}

async function compileInputCsv() {
  inputPopulationStatus.textContent = "";
  const file = inputCsvFile.files[0];
  if (!file || !currentWritePlan || !currentExecutionReceipt) {
    inputPopulationStatus.textContent = "Execute a ready write plan and select a CSV file first.";
    return;
  }
  compileInputCsvButton.disabled = true;
  try {
    const inputSet = await requestJson("/api/v1/workbooks/input-sets/from-csv", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contract_version: "workbook-input-set-csv-request.v1",
        source_name: file.name,
        csv_base64: await fileToBase64(file),
        write_plan: currentWritePlan,
        execution_receipt: currentExecutionReceipt,
      }),
    });
    currentInputSet = inputSet;
    inputSetEditor.value = JSON.stringify(inputSet, null, 2);
    inputPopulationStatus.textContent = "CSV compiled into a complete, pinned input set.";
    showResult("Workbook input set", inputSet);
  } catch (error) {
    currentInputSet = null;
    inputPopulationStatus.textContent = error.message;
  } finally {
    refreshInputPopulationButtons();
  }
}

async function populateInputs() {
  inputPopulationStatus.textContent = "";
  if (!currentExecutedWorkbookBase64 || !currentExecutionReceipt || !currentWritePlan) {
    inputPopulationStatus.textContent = "Execute the accepted write plan before input population.";
    return;
  }
  populateInputsButton.disabled = true;
  try {
    const inputSet = parseInputSetEditor();
    if (!inputSet) throw new Error("Paste or compile workbook-input-set.v1 JSON first.");
    const result = await requestJson("/api/v1/workbooks/input-populations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contract_version: "workbook-input-population-request.v1",
        filename: currentExecutedWorkbookFilename,
        output_filename: populatedWorkbookName(currentExecutedWorkbookFilename),
        workbook_base64: currentExecutedWorkbookBase64,
        write_plan: currentWritePlan,
        execution_receipt: currentExecutionReceipt,
        input_set: inputSet,
      }),
    });
    currentInputSet = inputSet;
    currentInputPopulationReceipt = result.receipt;
    currentPopulatedWorkbookBase64 = result.workbook_base64;
    currentPopulatedWorkbookFilename = result.output_filename;
    downloadBase64Workbook(result.output_filename, result.workbook_base64);
    showResult("Input population receipt", result.receipt);
    inputPopulationStatus.textContent = `Downloaded ${result.output_filename}. Input values are excluded from the receipt.`;
  } catch (error) {
    currentInputPopulationReceipt = null;
    currentPopulatedWorkbookBase64 = null;
    currentPopulatedWorkbookFilename = null;
    inputPopulationStatus.textContent = error.message;
  } finally {
    refreshInputPopulationButtons();
    if (typeof refreshCalculationButton === "function") refreshCalculationButton();
  }
}

inputCsvFile.addEventListener("change", refreshInputPopulationButtons);
inputSetEditor.addEventListener("input", () => {
  currentInputSet = null;
  currentInputPopulationReceipt = null;
  currentPopulatedWorkbookBase64 = null;
  currentPopulatedWorkbookFilename = null;
  refreshInputPopulationButtons();
});
compileInputCsvButton.addEventListener("click", compileInputCsv);
populateInputsButton.addEventListener("click", populateInputs);

const inputPopulationResultObserver = new MutationObserver(() => {
  if (currentResult?.contract_version === "workbook-execution-receipt.v1") {
    invalidateInputPopulation();
  }
});
inputPopulationResultObserver.observe(document.querySelector("#result-output"), {
  childList: true,
  characterData: true,
  subtree: true,
});

for (const target of [workbookFile, editor, forecastPeriodCount, writeContextEditor, fixtureSelect]) {
  target.addEventListener(
    target === editor || target === forecastPeriodCount || target === writeContextEditor ? "input" : "change",
    invalidateInputPopulation,
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
  button.addEventListener("click", invalidateInputPopulation);
}

validateDisplayedButton.addEventListener("click", async (event) => {
  if (currentResult?.contract_version !== "workbook-input-population-receipt.v1") return;
  event.preventDefault();
  event.stopImmediatePropagation();
  setStatus();
  try {
    const result = await requestJson("/api/v1/workbooks/input-population-receipts/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        receipt: currentResult,
        input_set: currentInputSet,
        write_plan: currentWritePlan,
        execution_receipt: currentExecutionReceipt,
      }),
    });
    showResult("Input population receipt validation", result);
  } catch (error) {
    setStatus(error.message);
  }
}, true);

refreshInputPopulationButtons();
