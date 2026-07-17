# SaaS Budget & Forecast Workbook

FMR includes a practitioner-facing SaaS Budget & Forecast workflow.

This workflow is designed for finance managers, FP&A practitioners and operators who want a repeatable workbook structure without handling provider manifests, handoff JSON or internal routing contracts.

## What it generates

The workflow creates an `.xlsx` workbook with these sheets:

- Summary
- Assumptions
- ARR Bridge
- Revenue Forecast
- Opex & Headcount
- Cash Runway
- Scenarios
- Checks

The workbook contains formulas for ARR movement, retention, revenue, gross profit, opex, EBITDA proxy, free cash flow proxy, cash runway and basic checks.

## Browser workflow

Install with the workbook extra and start the local app:

```bash
python -m pip install -e ".[dev-ui,executor]"
fmr serve
```

Open:

```text
http://127.0.0.1:8000/practitioner/saas
```

Enter assumptions in the form and generate the Excel workbook.

## CLI workflow

Generate a workbook from the bundled example assumptions:

```bash
fmr saas-budget-workbook \
  --input-json examples/saas_budget_inputs.json \
  --output outputs/saas-budget-forecast.xlsx
```

Or generate one directly from CLI flags:

```bash
fmr saas-budget-workbook \
  --company-name "Example SaaS Company" \
  --opening-arr 1200000 \
  --monthly-new-arr 50000 \
  --monthly-expansion-arr 15000 \
  --monthly-contraction-arr 5000 \
  --monthly-churned-arr 10000 \
  --starting-cash 1500000 \
  --output outputs/saas-budget-forecast.xlsx
```

## Boundary

FMR does not provide accounting, tax, investment, valuation or lending advice. This workflow creates a structured planning workbook and checks. Practitioners must review assumptions, formulas and outputs before using the workbook.
