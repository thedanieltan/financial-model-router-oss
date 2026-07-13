# Financial Model Router

Financial Model Router (FMR) is an open-source Python toolkit for selecting a financial-model architecture, checking whether the available inputs are sufficient, inspecting XLSX workbook structure, and producing controlled transformation, patch and target plans.

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

FMR publishes a versioned operation specification registry and resolves each patch operation to an existing, new, planned, set or blocked workbook target in `workbook-target-resolution.v1`. It does not assign write coordinates or execute the patch.

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
fmr validate-target-resolution target-resolution.json \
  --analysis workbook-analysis.json \
  --patch workbook-patch.json
```

Only `.xlsx` files are accepted. Inspection, analysis, patch compilation and target resolution do not modify the source workbook.

## Design rules

- Model selection is explainable.
- Missing information is reported, not invented.
- Workbook classification includes evidence and confidence.
- Workbook-derived inputs require medium or high confidence and sufficient period evidence.
- Assumptions are never inferred from workbook labels.
- Formulas are read as text and never executed.
- Patch operations are additive, closed-vocabulary intents without formulas or cell writes.
- Patch and target IDs pin their source contracts.
- Ambiguous semantic targets are blocked.
- Workbook execution requires a separate accepted executor.
- Public fixtures are synthetic and generated during tests.
- CLI, Python and HTTP interfaces call the same deterministic functions.

See [docs/SERVICE.md](docs/SERVICE.md), [docs/WORKBOOK_INSPECTION.md](docs/WORKBOOK_INSPECTION.md), [docs/WORKBOOK_ANALYSIS.md](docs/WORKBOOK_ANALYSIS.md), [docs/WORKBOOK_PATCH.md](docs/WORKBOOK_PATCH.md), [docs/SEMANTIC_TARGET_RESOLUTION.md](docs/SEMANTIC_TARGET_RESOLUTION.md), [docs/DEVELOPER_WORKBENCH.md](docs/DEVELOPER_WORKBENCH.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/IP_BOUNDARY.md](docs/IP_BOUNDARY.md).

## Licence

Apache License 2.0.
