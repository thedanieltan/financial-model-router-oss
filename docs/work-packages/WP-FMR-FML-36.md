# WP-FMR-FML-36 — Dry-run monthly FP&A formula plan

## Outcome

Connect the read-only workbook semantic map to FMR's governed formula registry by producing a deterministic dry-run plan for monthly FP&A formula extension.

## Included

- `workbook-formula-plan.v1` provider-owned contract plus byte-identical compatibility copy;
- deterministic selection of a monthly income-statement or budget/forecast target;
- exact target-cell and source-cell bindings;
- governed `fmr.formula.forecast_column_copy.v1` references rather than raw generated Excel formula text;
- chained planning where later forecast cells may depend on earlier planned cells;
- explicit unresolved targets and fail-closed readiness;
- plan-level validation references;
- `fmr formula-plan` CLI;
- schema, deterministic-recomputation, read-only and CLI tests.

## Excluded

Workbook mutation, executor integration, invention of driver assumptions, LLM semantic guessing, overwriting existing nonblank cells, and practitioner/deployment/production acceptance.

## Acceptance gates

Implementation passes only when the plan is deterministic, schema-valid, source-byte-preserving, contains no raw formulas or financial values, fails closed on unsupported rows, uses only registered formula specifications, and the full repository CI remains green.

## Next

WP-FMR-FML-37 should add a driver-aware planning layer for first-forecast-period formulas. It may bind evidenced revenue, headcount, operating-cost and working-capital drivers, but must keep assumptions explicit and continue to produce a dry-run plan before any workbook write.
