# Service

Financial Model Router turns a modelling objective and a set of available inputs into:

1. a selected model family;
2. a readiness report;
3. a controlled transformation plan;
4. an optional governed workbook write plan;
5. an optional copied-workbook execution receipt; and
6. an optional calculated-output acceptance receipt.

## Supported model families

- Budget and forecast
- Integrated three-statement model
- Operating-company DCF
- Debt-capacity and refinancing analysis

## Inputs

The routing interface accepts JSON containing:

- `objective`;
- `role`;
- `available_data`;
- `workbook_capabilities`; and
- `assumptions`.

Workbook workflows additionally accept versioned FMR contracts and `.xlsx` bytes or file paths.

## Outputs

`route` returns a recommendation and readiness report. `plan` adds ordered transformation operations.

The workbook pipeline can return versioned map, analysis, patch, target, coordinate, content, realization, write-plan, execution-receipt and calculation-acceptance documents. Successful execution and calculation commands write only to new output paths.

## Boundaries

FMR does not:

- keep books;
- calculate tax;
- provide investment advice;
- forecast market prices;
- upload user files to a remote service;
- invent missing data;
- overwrite a source workbook;
- execute macros or external workbook links;
- preserve unsupported charts, pivots or drawings through the executor; or
- record input or calculated cell values in execution and calculation receipts.

Live formula calculation is delegated to an optional spreadsheet engine. FMR validates the resulting cached values against declared contracts but does not replace financial review.
