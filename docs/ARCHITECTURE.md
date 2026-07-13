# Architecture

```text
model-request.v1
      |
      v
objective normalization
      |
      v
model definition registry
      |
      +--> recommendation
      |
      +--> readiness assessment
                 |
                 v
       transformation-plan.v1
```

## Modules

- `fmr.router`: objective normalization and model selection.
- `fmr.readiness`: required-input comparison.
- `fmr.plan`: ordered, closed-vocabulary transformation plans.
- `fmr.model_specs`: supported model definitions.
- `fmr.contracts`: packaged JSON schemas.

The core uses only the Python standard library.

## Control boundary

The planner can emit only approved operation types. It does not emit formulas or cell writes. Workbook mutation will be implemented as a separate layer with preconditions, rollback, and file-level verification.
