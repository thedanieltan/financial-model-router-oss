# Service

Financial Model Router turns a modelling objective and a set of available inputs into:

1. a selected model family;
2. a readiness report; and
3. a controlled transformation plan.

## Supported model families

- Budget and forecast
- Integrated three-statement model
- Operating-company DCF
- Debt-capacity and refinancing analysis

## Inputs

The current interface accepts JSON containing:

- `objective`;
- `role`;
- `available_data`;
- `workbook_capabilities`; and
- `assumptions`.

## Outputs

`route` returns a recommendation and readiness report. `plan` adds ordered transformation operations.

## Boundaries

FMR does not:

- keep books;
- calculate tax;
- provide investment advice;
- forecast market prices;
- upload user files;
- invent missing data; or
- edit an Excel file in the current release.
