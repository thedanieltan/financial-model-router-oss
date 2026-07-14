# Financial Model Router

Financial Model Router (FMR) is an open-source Python toolkit for financial-data intake, model selection, controlled workbook construction, governed input population and calculated-output validation.

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

FMR 0.4.2 compiles explicit numeric or boolean CSV data into `workbook-input-set.v1`, populates only ranges governed by `reserve_input` records, and emits `workbook-input-population-receipt.v1` without input values.

FMR 0.5 normalizes provider-neutral statement CSVs into `financial-data-package.v1`, maps exact account labels or explicit overrides to canonical concepts, binds concepts or constants to semantic workbook slot IDs, and emits `workbook-input-set.v1` only when every reserved numeric or boolean input is covered.

Derived evidence never creates assumptions and never overrides explicit user input.

## Install

Planning and financial-data intake:

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

Financial-data intake:

```bash
fmr financial-concepts --output concepts.json
fmr import-statement-csv statements.csv --output financial-data-package.json
fmr make-financial-mapping-profile mapping-rules.json --output mapping-profile.json
fmr map-financial-data financial-data-package.json \
  --profile mapping-profile.json \
  --output mapping-result.json
fmr make-financial-binding-profile slot-bindings.json --output binding-profile.json
fmr plan-financial-bindings \
  financial-data-package.json mapping-result.json binding-profile.json \
  write-plan.json execution-receipt.json \
  --output input-binding-plan.json
fmr compile-financial-input-set \
  input-binding-plan.json write-plan.json execution-receipt.json \
  --output input-set.json
```

Workbook pipeline:

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
fmr plan-writes realization-plan.json write-context.json --output write-plan.json
fmr execute-writes source.xlsx write-plan.json \
  --output executed.xlsx \
  --receipt execution-receipt.json
fmr populate-inputs executed.xlsx input-set.json write-plan.json execution-receipt.json \
  --output populated.xlsx \
  --receipt population-receipt.json
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
- Financial source amounts retain decimal precision during normalization.
- Account mapping uses exact aliases or explicit overrides; fuzzy matching is not used.
- Unmapped, ambiguous and statement-shape-invalid rows remain visible.
- Binding profiles use semantic slot IDs rather than write-record IDs.
- A governed input set is emitted only when every reserved input is covered.
- Assumptions are never inferred from workbook labels or financial statements.
- Existing formulas are inspected as text and never executed during inspection.
- Every plan and receipt pins its source contracts.
- Ambiguous semantic targets and dependency bindings are blocked.
- Coordinate ranges are checked against occupancy and Excel bounds.
- Formula templates use declared dependencies and forbid raw external references and circularity.
- Input slots are editable; generated output and control slots are locked.
- Execution verifies source identity and publishes atomically.
- Input-set values are never copied into population receipts.
- Calculation runs through an optional isolated spreadsheet-engine adapter.
- Formula errors and missing cached results block acceptance.
- Public fixtures and workbooks are synthetic and generated during tests.
- CLI, Python and HTTP interfaces call the same deterministic functions.

See [docs/FINANCIAL_DATA_INTAKE.md](docs/FINANCIAL_DATA_INTAKE.md), [docs/SERVICE.md](docs/SERVICE.md), [docs/WORKBOOK_INSPECTION.md](docs/WORKBOOK_INSPECTION.md), [docs/WORKBOOK_ANALYSIS.md](docs/WORKBOOK_ANALYSIS.md), [docs/WORKBOOK_PATCH.md](docs/WORKBOOK_PATCH.md), [docs/SEMANTIC_TARGET_RESOLUTION.md](docs/SEMANTIC_TARGET_RESOLUTION.md), [docs/COORDINATE_PLANNING.md](docs/COORDINATE_PLANNING.md), [docs/CONTENT_PLANNING.md](docs/CONTENT_PLANNING.md), [docs/FORMULA_STYLE_SPECIFICATIONS.md](docs/FORMULA_STYLE_SPECIFICATIONS.md), [docs/WRITE_PLANNING.md](docs/WRITE_PLANNING.md), [docs/WORKBOOK_EXECUTION.md](docs/WORKBOOK_EXECUTION.md), [docs/INPUT_POPULATION.md](docs/INPUT_POPULATION.md), [docs/CALCULATED_OUTPUT_ACCEPTANCE.md](docs/CALCULATED_OUTPUT_ACCEPTANCE.md), [docs/DEVELOPER_WORKBENCH.md](docs/DEVELOPER_WORKBENCH.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/IP_BOUNDARY.md](docs/IP_BOUNDARY.md).

## Licence

Apache License 2.0.
