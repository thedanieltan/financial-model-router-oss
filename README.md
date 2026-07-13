# Financial Model Router

Financial Model Router (FMR) is an open-source Python toolkit for selecting a financial-model architecture, checking whether the available inputs are sufficient, and producing a controlled transformation plan.

FMR does not provide accounting, tax, investment advice, or unrestricted spreadsheet editing. Its core is deterministic and runs locally.

## Current scope

The first release supports four model families:

- budget and forecast;
- integrated three-statement model;
- operating-company discounted cash-flow valuation; and
- debt-capacity and refinancing analysis.

Given a JSON request, FMR returns:

- the selected model family;
- the reasons for the selection;
- available and missing inputs;
- readiness blockers; and
- a machine-readable transformation plan.

It does not yet modify an Excel file. Workbook writing is a later, separately validated layer.

## Install the core

```bash
python -m pip install -e .
```

## Run the developer workbench

```bash
python -m pip install -e ".[dev-ui]"
fmr serve
```

Open `http://127.0.0.1:8000` for the browser workbench or `http://127.0.0.1:8000/docs` for the interactive API documentation.

The server binds to the loopback interface by default, stores no requests, sends no telemetry, and makes no outbound network calls.

## Use the CLI

```bash
fmr route tests/fixtures/request-dcf-ready.json
fmr plan tests/fixtures/request-dcf-ready.json
fmr validate-plan plan.json
python -m unittest discover -s tests -v
```

## Input example

```json
{
  "contract_version": "model-request.v1",
  "objective": "value an operating company using a DCF",
  "role": "finance_manager",
  "available_data": [
    "income_statement_history",
    "balance_sheet_history",
    "cash_flow_history",
    "revenue_drivers",
    "capital_expenditure_schedule",
    "working_capital_schedule",
    "net_debt"
  ],
  "workbook_capabilities": [
    "historical_periods",
    "assumptions_section"
  ],
  "assumptions": [
    "forecast_horizon",
    "tax_rate",
    "discount_rate",
    "terminal_value_assumption"
  ]
}
```

## Design rules

- Model selection is explainable.
- Missing information is reported, not invented.
- Formulas and workbook mutations require approved specifications.
- Existing workbooks must be copied rather than overwritten.
- Public fixtures are synthetic and independently authored.
- CLI, Python and HTTP interfaces use the same deterministic functions.

See [docs/SERVICE.md](docs/SERVICE.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DEVELOPER_WORKBENCH.md](docs/DEVELOPER_WORKBENCH.md), and [docs/IP_BOUNDARY.md](docs/IP_BOUNDARY.md).

## Licence

Apache License 2.0.
