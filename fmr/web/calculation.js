const calculationFile = document.querySelector("#calculation-file");
const calculateOutputButton = document.querySelector("#calculate-output-button");
const calculationEngineStatus = document.querySelector("#calculation-engine-status");
let currentCalculationAcceptance = null;
let calculationEngineAvailable = false;

function calculatedWorkbookName(filename) {
  return filename.replace(/\.xlsx$/i, "-calculated.xlsx");
}

function refreshCalculationButton() {
  const hasWorkbook = Boolean(
    calculationFile.files[0]
    || currentPopulatedWorkbookBase64
    || currentExecutedWorkbookBase64
  );
  calculateOutputButton.disabled = !(
    calculationEngineAvailable
    && hasWorkbook
    && currentExecutionReceipt
    && currentWritePlan
  );
}

function invalidateCalculation() {
  currentCalculationAcceptance = null;
  refreshCalculationButton();
}

async function checkCalculationEngine() {
  try {
    const status = await requestJson("/api/v1/calculation-engine");
    calculationEngineAvailable = status.available === true;
    calculationEngineStatus.textContent = calculationEngineAvailable
      ? `${status.engine.name} available`
      : status.error;
  } catch (error) {
    calculationEngineAvailable = false;
    calculationEngineStatus.textContent = error.message;
  }
  refreshCalculationButton();
}

async function calculateOutput() {
  workbookStatus.textContent = "";
  if (!currentExecutionReceipt || !currentWritePlan) {
    workbookStatus.textContent = "Execute the accepted write plan before calculation.";
    return;
  }
  const selected = calculationFile.files[0];
  const usesGovernedPopulation = Boolean(
    !selected
    && currentPopulatedWorkbookBase64
    && currentInputPopulationReceipt
  );
  const inputFilename = selected?.name
    || currentPopulatedWorkbookFilename
    || currentExecutedWorkbookFilename;
  const encoded = selected
    ? await fileToBase64(selected)
    : currentPopulatedWorkbookBase64 || currentExecutedWorkbookBase64;
  if (!inputFilename || !encoded) {
    workbookStatus.textContent = "Select or generate a populated executed workbook.";
    return;
  }
  calculateOutputButton.disabled = true;
  try {
    const result = await requestJson("/api/v1/workbooks/calculations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contract_version: "workbook-calculation-request.v1",
        filename: inputFilename,
        output_filename: calculatedWorkbookName(inputFilename),
        workbook_base64: encoded,
        write_plan: currentWritePlan,
        execution_receipt: currentExecutionReceipt,
        timeout_seconds: 120,
      }),
    });
    currentCalculationAcceptance = result.acceptance;
    if (usesGovernedPopulation) {
      const link = await requestJson(
        "/api/v1/workbooks/input-population-receipts/validate-calculation-link",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            population_receipt: currentInputPopulationReceipt,
            calculation_acceptance: result.acceptance,
          }),
        },
      );
      if (!link.valid) {
        throw new Error(`Calculated output is not linked to the governed input population: ${link.issues.join("; ")}`);
      }
    }
    if (result.workbook_base64) {
      downloadBase64Workbook(result.output_filename, result.workbook_base64);
      workbookStatus.textContent = usesGovernedPopulation
        ? `Calculated output passed, the input-population hash chain was verified, and ${result.output_filename} was downloaded.`
        : `Calculated output passed and ${result.output_filename} was downloaded.`;
    } else {
      workbookStatus.textContent = "Calculated output failed acceptance. No workbook was downloaded.";
    }
    showResult("Calculated-output acceptance", result.acceptance);
  } catch (error) {
    currentCalculationAcceptance = null;
    workbookStatus.textContent = error.message;
  } finally {
    refreshCalculationButton();
  }
}

calculationFile.addEventListener("change", invalidateCalculation);
calculateOutputButton.addEventListener("click", calculateOutput);

const calculationResultObserver = new MutationObserver(() => {
  if (
    currentResult?.contract_version === "workbook-execution-receipt.v1"
    || currentResult?.contract_version === "workbook-input-population-receipt.v1"
  ) {
    refreshCalculationButton();
  }
});
calculationResultObserver.observe(document.querySelector("#result-output"), {
  childList: true,
  characterData: true,
  subtree: true,
});

for (const target of [workbookFile, editor, forecastPeriodCount, writeContextEditor, fixtureSelect]) {
  target.addEventListener(
    target === editor || target === forecastPeriodCount || target === writeContextEditor ? "input" : "change",
    invalidateCalculation,
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
  populateInputsButton,
  document.querySelector("#reset-button"),
]) {
  button.addEventListener("click", invalidateCalculation);
}

validateDisplayedButton.addEventListener("click", async (event) => {
  if (currentResult?.contract_version !== "workbook-calculation-acceptance.v1") return;
  event.preventDefault();
  event.stopImmediatePropagation();
  setStatus();
  try {
    const result = await requestJson("/api/v1/workbooks/calculation-acceptances/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        acceptance: currentResult,
        write_plan: currentWritePlan,
        execution_receipt: currentExecutionReceipt,
      }),
    });
    showResult("Calculation acceptance validation", result);
  } catch (error) {
    setStatus(error.message);
  }
}, true);

checkCalculationEngine();
