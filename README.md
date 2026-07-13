# Financial Model Router

Financial Model Router (FMR) is an open-source Python toolkit for selecting a financial-model architecture, checking input sufficiency, inspecting XLSX structure, producing controlled workbook plans, executing those plans on copied workbooks, populating governed inputs and validating recalculated outputs.

FMR does not provide accounting, tax or investment advice. The deterministic core runs locally.

## Current scope

FMR supports four model families:

- budget and forecast;
- integrated three-statement model;
- operating-company discounted cash-flow valuation; and
- debt-capacity and refinancing analysis.

Given a JSON request, FMR returns the selected model family, reasons, readiness blockers and a machine-readable transformation plan.

FMR can inspect an `.xlsx` workbook and return `workbook-map.v1`. It can derive evidence-backed inputs, merge them with an explicit `model-request.v1`, and return `workbook-analysis.v1`.

A valid analysis can be compiled through versioned patch, target, coordinate, content, formula, style and write contracts. `workbook-write-plan.v1` contains explicit Excel A1 formulas and ordered sheet, value, input and style records.

FMR 0.4 applies an accepted write plan to a copied `.xlsx` workbook and emits `workbook-execution-receipt.v1` without cell values or workbook bytes.

FMR 0.4.1 recalculates a populated copy through optional LibreOffice, or accepts a workbook recalculated elsewhere. `workbook-calculation-acceptance.v1` checks immutable records, populated inputs, cached results, result types, sign conventions and spreadsheet errors without recording input or calculated values.

FMR 0.4.2 compiles explicit numeric or boolean CSV data into `workbook-input-set.v1`, populates only ranges governed by `reserve_input` records, and emits `workbook-input-population-receipt.v1`. Input sets contain values; population receipts contain only hashes, counts, record identifiers and statuses.

Derived evidence never creates assumptions and never overrides explicit user input.

## Install

Planning core:

```bash
python -m pip install -e .
```

Workbook execution, input population and calculated-output validation:

```bash
python -m pip install -e ".[executor]"
```

Local recalculation additionally requires LibreOffice with the `libreoffice` or `soffice` command available. A workbook recalculated in another spreadsheet engine can be validated without invoking LibreOffice from FMR.

Developer workbench:

```bash
python -m pip install -e ".[dev-ui,executor]"
fmr serve
```

Open `http://127.0.0.1:8000` for the browser workbench or `http://127.0.0.1:8000/docs` for the API console.

The server binds to the loopback interface, stores no requests, sends no telemetry and makes no outbound network calls.

## Use the CLI

```bash
fmr route tests/fixtures/request-dcf-ready.json
fmr plan tests/fixtures/request-debt-blocked.json
fmr inspect model.xlsx --output workbook-map.json
fmr analyse-workbook model.xlsx request.json --output workbook-analysis.json
fmr compile-patch workbook-analysis.json --output workbook-patch.json
fmr resolve-targets workbook-analysis.json workbook-patch.json \
  --output target-resolution.json
fmr plan-coordinates workbook-analysis.json workbook-patch.json target-resolution.json \
  --forecast-period-count 5 \
  --output coordinate-plan.json
fmr plan-content coordinate-plan.json --output content-plan.json
fmr plan-realization content-plan.json --output realization-plan.json
fmr plan-writes realization-plan.json write-context.json \
  --output write-plan.json
fmr execute-writes source.xlsx write-plan.json \
  --output executed.xlsx \
  --receipt execution-receipt.json
fmr compile-input-set-csv inputs.csv write-plan.json execution-receipt.json \
  --output input-set.json
fmr populate-inputs executed.xlsx input-set.json write-plan.json execution-receipt.json \
  --output populated.xlsx \
  --receipt population-receipt.json
fmr calculation-engine-status
fmr calculate-output populated.xlsx write-plan.json execution-receipt.json \
  --output calculated.xlsx \
  --receipt calculation-acceptance.json
fmr validate-input-calculation-link \
  population-receipt.json calculation-acceptance.json
```

Only `.xlsx` workbooks are accepted.

Planning through `validate-write-plan` is non-mutating. Execution, input population and calculation each publish only to a new output path. Calculated workbook bytes are published only after acceptance passes.

## Design rules

- Model selection is explainable.
- Missing information is reported, not invented.
- Workbook classification includes evidence and confidence.
- Assumptions are never inferred from workbook labels.
- Existing formulas are inspected as text and never executed during inspection.
- Patch operations are additive, closed-vocabulary intents.
- Every plan and receipt pins its source contracts.
- Ambiguous semantic targets and dependency bindings are blocked.
- Coordinate ranges are checked against occupancy and Excel bounds.
- Formula templates use declared dependencies and forbid raw external references and circularity.
- Style and number-format rules remain separate from financial-model logic.
- Input slots are editable; generated output and control slots are locked.
- Execution verifies source identity and publishes atomically.
- Input population writes only complete, explicitly bound reserved ranges.
- Input-set values are never copied into population receipts.
- Calculation runs through an optional isolated spreadsheet-engine adapter.
- Calculated outputs must preserve immutable records and populated inputs.
- Formula errors and missing cached results block acceptance.
- Public fixtures and workbooks are synthetic and generated during tests.
- CLI, Python and HTTP interfaces call the same deterministic functions.

See [docs/SERVICE.md](docs/SERVICE.md), [docs/WORKBOOK_INSPECTION.md](docs/WORKBOOK_INSPECTION.md), [docs/WORKBOOK_ANALYSIS.md](docs/WORKBOOK_ANALYSIS.md), [docs/WORKBOOK_PATCH.md](docs/WORKBOOK_PATCH.md), [docs/SEMANTIC_TARGET_RESOLUTION.md](docs/SEMANTIC_TARGET_RESOLUTION.md), [docs/COORDINATE_PLANNING.md](docs/COORDINATE_PLANNING.md), [docs/CONTENT_PLANNING.md](docs/CONTENT_PLANNING.md), [docs/FORMULA_STYLE_SPECIFICATIONS.md](docs/FORMULA_STYLE_SPECIFICATIONS.md), [docs/WRITE_PLANNING.md](docs/WRITE_PLANNING.md), [docs/WORKBOOK_EXECUTION.md](docs/WORKBOOK_EXECUTION.md), [docs/INPUT_POPULATION.md](docs/INPUT_POPULATION.md), [docs/CALCULATED_OUTPUT_ACCEPTANCE.md](docs/CALCULATED_OUTPUT_ACCEPTANCE.md), [docs/DEVELOPER_WORKBENCH.md](docs/DEVELOPER_WORKBENCH.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/IP_BOUNDARY.md](docs/IP_BOUNDARY.md).

## Licence

Apache License 2.0.
