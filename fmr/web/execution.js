const executeWorkbookButton = document.querySelector("#execute-workbook-button");
let currentExecutionReceipt = null;
let currentExecutedWorkbookBase64 = null;
let currentExecutedWorkbookFilename = null;

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      const value = String(reader.result || "");
      const separator = value.indexOf(",");
      if (separator < 0) reject(new Error("Could not encode the workbook."));
      else resolve(value.slice(separator + 1));
    });
    reader.addEventListener("error", () => reject(reader.error || new Error("Could not read the workbook.")));
    reader.readAsDataURL(file);
  });
}

function downloadBase64Workbook(filename, encoded) {
  const binary = atob(encoded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  const blob = new Blob([bytes], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function copiedWorkbookName(filename) {
  return filename.replace(/\.xlsx$/i, "-fmr.xlsx");
}

function invalidateExecution() {
  currentExecutionReceipt = null;
  currentExecutedWorkbookBase64 = null;
  currentExecutedWorkbookFilename = null;
  executeWorkbookButton.disabled = true;
}

async function executeCopiedWorkbook() {
  workbookStatus.textContent = "";
  const file = workbookFile.files[0];
  if (!file || !currentWritePlan) {
    workbookStatus.textContent = "Select the inspected workbook and compile a ready write plan first.";
    return;
  }
  if (currentWritePlan.ready_for_executor !== true) {
    workbookStatus.textContent = "The write plan is blocked and cannot be executed.";
    return;
  }
  executeWorkbookButton.disabled = true;
  try {
    const outputFilename = copiedWorkbookName(file.name);
    const result = await requestJson("/api/v1/workbooks/executions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contract_version: "workbook-execution-request.v1",
        filename: file.name,
        output_filename: outputFilename,
        workbook_base64: await fileToBase64(file),
        write_plan: currentWritePlan,
      }),
    });
    currentExecutedWorkbookBase64 = result.workbook_base64;
    currentExecutedWorkbookFilename = result.output_filename;
    currentExecutionReceipt = result.receipt;
    downloadBase64Workbook(result.output_filename, result.workbook_base64);
    showResult("Workbook execution receipt", result.receipt);
    workbookStatus.textContent = `Downloaded ${result.output_filename}. The selected source file was not modified.`;
  } catch (error) {
    currentExecutionReceipt = null;
    currentExecutedWorkbookBase64 = null;
    currentExecutedWorkbookFilename = null;
    workbookStatus.textContent = error.message;
  } finally {
    executeWorkbookButton.disabled = !(currentWritePlan?.ready_for_executor === true);
  }
}

executeWorkbookButton.addEventListener("click", executeCopiedWorkbook);

const executionResultObserver = new MutationObserver(() => {
  if (currentResult?.contract_version === "workbook-write-plan.v1") {
    currentExecutionReceipt = null;
    currentExecutedWorkbookBase64 = null;
    currentExecutedWorkbookFilename = null;
    executeWorkbookButton.disabled = currentResult.ready_for_executor !== true;
  }
});
executionResultObserver.observe(document.querySelector("#result-output"), {
  childList: true,
  characterData: true,
  subtree: true,
});

for (const target of [workbookFile, editor, forecastPeriodCount, writeContextEditor, fixtureSelect]) {
  target.addEventListener(
    target === editor || target === forecastPeriodCount || target === writeContextEditor ? "input" : "change",
    invalidateExecution,
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
  document.querySelector("#reset-button"),
]) {
  button.addEventListener("click", invalidateExecution);
}

validateDisplayedButton.addEventListener("click", async (event) => {
  if (currentResult?.contract_version !== "workbook-execution-receipt.v1") return;
  event.preventDefault();
  event.stopImmediatePropagation();
  setStatus();
  try {
    const result = await requestJson("/api/v1/workbooks/execution-receipts/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        receipt: currentResult,
        write_plan: currentWritePlan,
      }),
    });
    showResult("Execution receipt validation", result);
  } catch (error) {
    setStatus(error.message);
  }
}, true);
