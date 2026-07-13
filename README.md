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

## Install

```bash
python -m pip install -e .
```

## Use

```bash
python -m fmr route tests/fixtures/request-dcf-ready.json
python -m fmr plan tests/fixtures/request-dcf-ready.json
python -m unittest discover -s tests -v
```

## Input example

```json
{
  "contract_version": "model-request.v1",
  "objective": "value an operating company",
  "role": "finance_manager",
  "available_data": [
    "income_statement_history",
    "balance_sheet_history",
    "cash_flow_history",
    "revenue_drivers",
    "tax_rate",
    "capital_expenditure_schedule",
    "working_capital_schedule",
    "discount_rate",
    "terminal_value_assumption",
    "net_debt"
  ],
  "workbook_capabilities": ["historical_periods", "assumptions_section"],
  "assumptions": ["forecast_horizon"]
}
```

## Design rules

- Model selection is explainable.
- Missing information is reported, not invented.
- Formulas and workbook mutations require approved specifications.
- Existing workbooks must be copied rather than overwritten.
- Public fixtures are synthetic and independently authored.

See [docs/SERVICE.md](docs/SERVICE.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/IP_BOUNDARY.md](docs/IP_BOUNDARY.md).

## Licence

Apache License 2.0.
