# Financial Model Router

Financial Model Router (FMR) is an open-source Python toolkit for selecting a financial-model architecture, checking whether the available inputs are sufficient, inspecting XLSX workbook structure, and producing a controlled transformation plan.

FMR does not provide accounting, tax, or investment advice. It does not modify workbooks in the current release. The core is deterministic and runs locally.

## Current scope

FMR supports four model families:

- budget and forecast;
- integrated three-statement model;
- operating-company discounted cash-flow valuation; and
- debt-capacity and refinancing analysis.

Given a JSON request, FMR returns the selected model family, reasons, readiness blockers and a machine-readable transformation plan.

FMR can inspect an `.xlsx` workbook and return `workbook-map.v1`. It can then derive evidence-backed inputs and workbook capabilities, merge them with an explicit `model-request.v1`, and return `workbook-analysis.v1`.

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
```

Only `.xlsx` files are accepted. Inspection and analysis do not modify the source workbook.

## Design rules

- Model selection is explainable.
- Missing information is reported, not invented.
- Workbook classification includes evidence and confidence.
- Workbook-derived inputs require medium or high confidence and sufficient period evidence.
- Assumptions are never inferred from workbook labels.
- Formulas are read as text and never executed.
- Workbook mutations require a separate approved specification.
- Public fixtures are synthetic and generated during tests.
- CLI, Python and HTTP interfaces call the same deterministic functions.

See [docs/SERVICE.md](docs/SERVICE.md), [docs/WORKBOOK_INSPECTION.md](docs/WORKBOOK_INSPECTION.md), [docs/WORKBOOK_ANALYSIS.md](docs/WORKBOOK_ANALYSIS.md), [docs/DEVELOPER_WORKBENCH.md](docs/DEVELOPER_WORKBENCH.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/IP_BOUNDARY.md](docs/IP_BOUNDARY.md).

## Licence

Apache License 2.0.
