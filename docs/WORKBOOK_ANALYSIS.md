# Workbook analysis

Workbook analysis connects `workbook-map.v1` to the existing routing, readiness and transformation-planning engine.

## Interfaces

```bash
fmr analyse-workbook model.xlsx request.json --output workbook-analysis.json
```

```text
POST /api/v1/workbooks/analyse
```

The HTTP endpoint accepts `workbook-analysis-request.v1`, containing a `workbook_map` and a `model_request`.

## Evidence rules

FMR derives only the following evidence in this release:

- historical income statement, balance sheet and cash-flow data from medium/high-confidence sheet classifications with at least two historical periods;
- debt schedules from medium/high-confidence debt-schedule sheets with at least two historical periods;
- net debt when a classified balance sheet contains both cash and debt metrics;
- historical and forecast period capabilities;
- assumptions-section and existing-formula capabilities.

Derived items include the sheet name, matched role, periods and classification evidence.

FMR does not infer assumptions, current values, forecast drivers, working-capital schedules, capital-expenditure schedules or liquidity positions from labels alone.

## Output

`workbook-analysis.v1` contains:

- the original workbook map;
- the original model request;
- derived evidence;
- the effective request after set-union enrichment;
- the model recommendation and readiness report; and
- the controlled transformation plan.

Explicit user inputs are preserved. Workbook evidence can add supported inputs but cannot remove or override them.
