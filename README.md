# Financial Model Router

Financial Model Router (FMR) is an open-source Python toolkit for selecting a financial-model architecture, checking whether the available inputs are sufficient, inspecting XLSX workbook structure, and producing controlled transformation, patch, target, coordinate, content, realization and write plans.

FMR does not provide accounting, tax, or investment advice. It does not modify workbooks in the current release. The core is deterministic and runs locally.

## Current scope

FMR supports four model families:

- budget and forecast;
- integrated three-statement model;
- operating-company discounted cash-flow valuation; and
- debt-capacity and refinancing analysis.

Given a JSON request, FMR returns the selected model family, reasons, readiness blockers and a machine-readable transformation plan.

FMR can inspect an `.xlsx` workbook and return `workbook-map.v1`. It can derive evidence-backed inputs, merge them with an explicit `model-request.v1`, and return `workbook-analysis.v1`.

A valid analysis can be compiled into `workbook-patch.v1`. The patch pins the source and analysis hashes, maps approved additive operations, defines rollback receipt requirements and lists output checks.

FMR publishes versioned operation, coordinate, content, formula and style registries. It resolves patch operations to workbook targets in `workbook-target-resolution.v1`, reserves collision-checked ranges in `workbook-coordinate-plan.v1`, assigns labels and symbolic identifiers in `workbook-content-plan.v1`, binds formula dependencies and declarative styles in `workbook-realization-plan.v1`, then compiles an ordered dry-run `workbook-write-plan.v1`.

The write plan contains explicit Excel A1 formula records, value and input records, style records and idempotent sheet setup records. It requires explicit period labels and external source or validation bindings. It does not execute those records or emit workbook bytes.

Derived evidence never creates assumptions and never overrides explicit user input.

## Install the core

```bash
python -m pip install -e .
```

## Run the developer workbench

```bash
python -m pip install -e ".[dev-ui]"
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
fmr validate-realization-plan realization-plan.json \
  --content-plan content-plan.json
fmr plan-writes realization-plan.json write-context.json \
  --output write-plan.json
fmr validate-write-plan write-plan.json \
  --realization-plan realization-plan.json \
  --write-context write-context.json
```

Only `.xlsx` files are accepted. Every command above is non-mutating.

## Design rules

- Model selection is explainable.
- Missing information is reported, not invented.
- Workbook classification includes evidence and confidence.
- Workbook-derived inputs require medium or high confidence and sufficient period evidence.
- Assumptions are never inferred from workbook labels.
- Existing workbook formulas are read as text and never executed.
- Patch operations are additive, closed-vocabulary intents.
- Every plan pins its source contracts and registries.
- Ambiguous semantic targets and dependency bindings are blocked.
- Coordinate ranges are checked against source occupancy, prior allocations and Excel bounds.
- Variable forecast width and write-period labels must be supplied explicitly.
- Formula templates use declared FMR dependencies and forbid raw cell references and circularity.
- Write plans contain resolved Excel formulas but do not execute them.
- Style and number-format rules are separate from financial-model logic.
- Input slots are editable; generated output and control slots are locked.
- Workbook execution requires a separate accepted executor and output-validation gate.
- Public fixtures are synthetic and generated during tests.
- CLI, Python and HTTP interfaces call the same deterministic functions.

See [docs/SERVICE.md](docs/SERVICE.md), [docs/WORKBOOK_INSPECTION.md](docs/WORKBOOK_INSPECTION.md), [docs/WORKBOOK_ANALYSIS.md](docs/WORKBOOK_ANALYSIS.md), [docs/WORKBOOK_PATCH.md](docs/WORKBOOK_PATCH.md), [docs/SEMANTIC_TARGET_RESOLUTION.md](docs/SEMANTIC_TARGET_RESOLUTION.md), [docs/COORDINATE_PLANNING.md](docs/COORDINATE_PLANNING.md), [docs/CONTENT_PLANNING.md](docs/CONTENT_PLANNING.md), [docs/FORMULA_STYLE_SPECIFICATIONS.md](docs/FORMULA_STYLE_SPECIFICATIONS.md), [docs/WRITE_PLANNING.md](docs/WRITE_PLANNING.md), [docs/DEVELOPER_WORKBENCH.md](docs/DEVELOPER_WORKBENCH.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/IP_BOUNDARY.md](docs/IP_BOUNDARY.md).

## Licence

Apache License 2.0.
