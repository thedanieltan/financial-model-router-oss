# Financial Model Router

Financial Model Router (FMR) is an open-source Python toolkit for selecting a financial-model architecture, checking whether the available inputs are sufficient, inspecting XLSX workbook structure, producing controlled workbook plans, applying an accepted plan to a copied workbook, and validating recalculated outputs.

FMR does not provide accounting, tax, or investment advice. The deterministic core runs locally.

## Current scope

FMR supports four model families:

- budget and forecast;
- integrated three-statement model;
- operating-company discounted cash-flow valuation; and
- debt-capacity and refinancing analysis.

Given a JSON request, FMR returns the selected model family, reasons, readiness blockers and a machine-readable transformation plan.

FMR can inspect an `.xlsx` workbook and return `workbook-map.v1`. It can derive evidence-backed inputs, merge them with an explicit `model-request.v1`, and return `workbook-analysis.v1`.

A valid analysis can be compiled through versioned patch, target, coordinate, content, formula, style and write contracts. `workbook-write-plan.v1` contains explicit Excel A1 formulas and ordered sheet, value, input and style records.

FMR 0.4 applies an accepted write plan to a copied `.xlsx` workbook. It validates the source hash, refuses to overwrite the source or an existing output, reopens and verifies the completed workbook, and emits `workbook-execution-receipt.v1` without cell values or workbook bytes.

FMR 0.4.1 optionally recalculates a populated copy through LibreOffice, or accepts a workbook recalculated elsewhere. `workbook-calculation-acceptance.v1` checks immutable records, populated input ranges, cached formula results, result types, sign conventions and spreadsheet errors without recording input or calculated values.

Derived evidence never creates assumptions and never overrides explicit user input.

## Install

Planning core:

```bash
python -m pip install -e .
```

Workbook execution and calculated-output validation:

```bash
python -m pip install -e ".[executor]"
```

Local recalculation additionally requires LibreOffice with the `libreoffice` or `soffice` command available. A workbook recalculated in another spreadsheet engine can be validated through the external-acceptance command without invoking LibreOffice from FMR.

Developer workbench with execution and calculated-output acceptance:

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
fmr operation-specs --output operation-specs.json
fmr resolve-targets workbook-analysis.json workbook-patch.json \
  --output target-resolution.json
fmr coordinate-rules --output coordinate-rules.json
fmr plan-coordinates workbook-analysis.json workbook-patch.json target-resolution.json \
  --forecast-period-count 5 \
  --output coordinate-plan.json
fmr content-specs --output content-specs.json
fmr plan-content coordinate-plan.json --output content-plan.json
fmr formula-specs --output formula-specs.json
fmr style-specs --output style-specs.json
fmr plan-realization content-plan.json --output realization-plan.json
fmr plan-writes realization-plan.json write-context.json \
  --output write-plan.json
fmr validate-write-plan write-plan.json \
  --realization-plan realization-plan.json \
  --write-context write-context.json
fmr execute-writes source.xlsx write-plan.json \
  --output completed.xlsx \
  --receipt execution-receipt.json
fmr validate-execution-receipt execution-receipt.json \
  --write-plan write-plan.json
fmr calculation-engine-status
fmr calculate-output populated.xlsx write-plan.json execution-receipt.json \
  --output calculated.xlsx \
  --receipt calculation-acceptance.json
fmr validate-calculation-acceptance calculation-acceptance.json \
  --write-plan write-plan.json \
  --execution-receipt execution-receipt.json
```

Only `.xlsx` files are accepted.

All commands through `validate-write-plan` are non-mutating. `execute-writes` writes only to a new output path. `calculate-output` publishes a separate recalculated workbook only after acceptance passes.

## Design rules

- Model selection is explainable.
- Missing information is reported, not invented.
- Workbook classification includes evidence and confidence.
- Workbook-derived inputs require medium or high confidence and sufficient period evidence.
- Assumptions are never inferred from workbook labels.
- Existing workbook formulas are read as text and never executed during inspection.
- Patch operations are additive, closed-vocabulary intents.
- Every plan pins its source contracts and registries.
- Ambiguous semantic targets and dependency bindings are blocked.
- Coordinate ranges are checked against source occupancy, prior allocations and Excel bounds.
- Variable forecast width, period labels and external bindings must be supplied explicitly.
- Formula templates use declared FMR dependencies and forbid raw cell references and circularity.
- Write plans contain resolved Excel formulas but remain dry runs.
- Style and number-format rules are separate from financial-model logic.
- Input slots are editable; generated output and control slots are locked.
- Execution verifies source identity, applies only an accepted write plan and publishes atomically.
- Calculation runs through an optional isolated spreadsheet-engine adapter.
- Calculated outputs must preserve immutable records and populated input values.
- Formula errors and missing cached results block calculated-output acceptance.
- Execution and calculation receipts contain hashes, types, signs and statuses, not cell values.
- Public fixtures and workbooks are synthetic and generated during tests.
- CLI, Python and HTTP interfaces call the same deterministic functions.

See [docs/SERVICE.md](docs/SERVICE.md), [docs/WORKBOOK_INSPECTION.md](docs/WORKBOOK_INSPECTION.md), [docs/WORKBOOK_ANALYSIS.md](docs/WORKBOOK_ANALYSIS.md), [docs/WORKBOOK_PATCH.md](docs/WORKBOOK_PATCH.md), [docs/SEMANTIC_TARGET_RESOLUTION.md](docs/SEMANTIC_TARGET_RESOLUTION.md), [docs/COORDINATE_PLANNING.md](docs/COORDINATE_PLANNING.md), [docs/CONTENT_PLANNING.md](docs/CONTENT_PLANNING.md), [docs/FORMULA_STYLE_SPECIFICATIONS.md](docs/FORMULA_STYLE_SPECIFICATIONS.md), [docs/WRITE_PLANNING.md](docs/WRITE_PLANNING.md), [docs/WORKBOOK_EXECUTION.md](docs/WORKBOOK_EXECUTION.md), [docs/CALCULATED_OUTPUT_ACCEPTANCE.md](docs/CALCULATED_OUTPUT_ACCEPTANCE.md), [docs/DEVELOPER_WORKBENCH.md](docs/DEVELOPER_WORKBENCH.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/IP_BOUNDARY.md](docs/IP_BOUNDARY.md).

## Licence

Apache License 2.0.
