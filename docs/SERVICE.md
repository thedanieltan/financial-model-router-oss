# Service

Financial Model Router turns a modelling objective and available inputs into:

1. a selected model family;
2. a readiness report;
3. a controlled transformation plan;
4. an optional governed workbook write plan;
5. an optional copied-workbook execution receipt;
6. an optional governed input set and value-free population receipt; and
7. an optional calculated-output acceptance receipt.

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

Governed input population accepts `workbook-input-set.v1` or UTF-8 CSV with one explicit finite numeric or boolean value per reserved input cell. Input sets are value-bearing working artifacts and should be handled accordingly.

## Outputs

`route` returns a recommendation and readiness report. `plan` adds ordered transformation operations.

The workbook pipeline can return versioned map, analysis, patch, target, coordinate, content, realization, write-plan, execution-receipt, input-set, population-receipt and calculation-acceptance documents. Successful execution, population and calculation commands write only to new output paths.

Execution, population and calculation receipts contain hashes, identifiers, counts and statuses rather than workbook cell values. The population-to-calculation link validator confirms that calculated acceptance consumed the exact governed population output.

## Boundaries

FMR does not:

- keep books;
- calculate tax;
- provide investment advice;
- forecast market prices;
- upload user files to a remote service;
- invent missing data;
- overwrite a source workbook;
- populate cells outside accepted `reserve_input` ranges;
- accept text, formulas, NaN or infinity as governed input values;
- execute macros or external workbook links;
- preserve unsupported charts, pivots or drawings through the executor; or
- record input or calculated cell values in execution, population or calculation receipts.

Live formula calculation is delegated to an optional spreadsheet engine. FMR validates cached results against declared contracts but does not replace financial review.
