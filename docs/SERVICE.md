# Service

## Target service

FMR routes a provider-neutral financial-modelling job to a compatible, versioned
model package. The router validates and classifies the request, discovers
packages without executing provider code, applies constraints, reports readiness,
ranks candidates under an explicit policy and compiles a pinned provider handoff.
Execution and validation are later lifecycle stages. A recognized model family
may legitimately produce a structured no-route result.

The current workbook service below remains operational during migration and is
the implementation that will become the Native XLSX provider. It is not the
router's product boundary. See [PRODUCT_CHARTER.md](PRODUCT_CHARTER.md).

## Current compatibility service

Financial Model Router turns financial source data, a modelling objective and an optional existing workbook into:

1. a normalized financial-data package;
2. an auditable account-mapping result;
3. a selected model family and readiness report;
4. a controlled transformation and workbook-write plan;
5. a copied-workbook execution receipt;
6. a governed input set and value-free population receipt; and
7. an optional calculated-output acceptance receipt.

## Supported model families

- Budget and forecast
- Integrated three-statement model
- Operating-company DCF
- Debt-capacity and refinancing analysis

## Inputs

The routing interface accepts `objective`, `role`, `available_data`, `workbook_capabilities` and `assumptions`.

The first financial-data adapter accepts one-entity UTF-8 statement CSVs with period, statement, account, amount and source-reference fields. Mapping profiles may supply exact account-code or account-name overrides. Binding profiles map semantic workbook slot IDs to canonical concepts or explicit numeric and boolean constants.

Workbook workflows accept versioned FMR contracts and `.xlsx` bytes or file paths.

## Outputs

The intake layer can return:

- `financial-data-package.v1`;
- `financial-data-mapping-profile.v1`;
- `financial-data-mapping-result.v1`;
- `financial-data-binding-profile.v1`; and
- `workbook-input-binding-plan.v1`.

A ready binding plan compiles into the existing `workbook-input-set.v1`. The remaining workbook pipeline returns map, analysis, patch, target, coordinate, content, realization, write-plan, execution, population and calculation-acceptance contracts.

Execution, population and calculation receipts contain hashes, identifiers, counts and statuses rather than workbook cell values.

## Boundaries

FMR does not:

- keep books or post journal entries;
- calculate tax or provide investment advice;
- infer missing financial values or assumptions;
- use fuzzy account mapping;
- silently resolve unmapped or conflicting accounts;
- consolidate entities or convert currencies;
- upload files to a remote service;
- overwrite source workbooks;
- populate cells outside accepted reserved ranges;
- accept text, formulas, NaN or infinity as governed input values;
- execute macros or external workbook links; or
- record input or calculated cell values in receipts.

Live formula calculation is delegated to an optional spreadsheet engine. FMR validates outputs against declared contracts but does not replace accounting or financial review.
