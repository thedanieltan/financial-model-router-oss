# Workbook write planning

`workbook-write-plan.v1` is the final non-mutating contract before the workbook executor.

It converts an accepted `workbook-realization-plan.v1` and an explicit `workbook-write-context.v1` into an ordered dry-run set of workbook actions.

## Inputs

The realization plan supplies:

- accepted sheets and coordinates;
- labels and input placeholders;
- FMR expression templates;
- resolved content-slot dependencies;
- semantic styles and number formats; and
- source and registry digests.

The write context supplies information FMR cannot infer safely:

- period labels;
- source-workbook ranges;
- validation ranges;
- reference targets; and
- numeric or boolean constants.

String formulas are not accepted as context values.

## Output phases

The plan emits four ordered phases:

1. `sheet_setup` — idempotently ensure each referenced sheet exists at its accepted position;
2. `values_and_inputs` — write FMR-owned labels and period headers and reserve blank editable input ranges;
3. `formulas_and_validations` — compile accepted `fmr-expression.v1` templates into explicit Excel A1 formulas; and
4. `styles_and_protection` — apply the accepted declarative style, number-format and protection records.

Every record has a deterministic sequence and record ID.

## Formula compilation

The compiler accepts only the functions registered by `fmr-expression.v1`. It resolves:

- content-slot dependencies to accepted coordinates;
- source, validation and reference dependencies through explicit context bindings;
- period indexes from deterministic fill position; and
- previous-period references from the accepted target coordinate.

Generated formulas:

- begin with `=`;
- contain no unresolved `{{tokens}}`;
- use absolute A1 references;
- contain no external workbook links;
- are never executed by this release; and
- are included only in the dry-run plan.

Missing or shape-incompatible bindings produce blockers. They are not guessed.

## Write context example

```json
{
  "contract_version": "workbook-write-context.v1",
  "period_labels": ["2024A", "2025A", "2026E", "2027E", "2028E"],
  "bindings": {
    "fmr.source.ebit.v1": {
      "binding_type": "range",
      "sheet_name": "Income Statement",
      "coordinate": "B12:F12",
      "alignment": "match"
    },
    "fmr.source.tax_rate.v1": {
      "binding_type": "constant",
      "value": 0.17
    },
    "fmr.validation-context.formula_consistency.v1": {
      "binding_type": "range",
      "sheet_name": "Checks",
      "coordinate": "B2:B20",
      "alignment": "whole_range"
    }
  }
}
```

## Interfaces

```bash
fmr plan-writes realization-plan.json write-context.json \
  --output write-plan.json

fmr validate-write-plan write-plan.json \
  --realization-plan realization-plan.json \
  --write-context write-context.json
```

HTTP:

```text
POST /api/v1/workbooks/write-plans
POST /api/v1/workbooks/write-plans/validate
```

The developer workbench displays a generated synthetic context for local testing. It remains visible and editable; it is not a production default.

## Boundary

This release does not:

- open an output workbook for writing;
- create, delete or rename worksheets;
- write labels, inputs or formulas;
- apply styles;
- calculate formulas;
- emit workbook bytes;
- replace the source file; or
- claim that a dry-run plan has been executed.

The executor must independently validate the source hash, accepted write plan, operation receipts and reopened output workbook.
