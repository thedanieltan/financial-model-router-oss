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

XLSX bytes
      |
      v
archive and XML validation
      |
      v
workbook-map.v1
      |
      + model-request.v1
      v
workbook-analysis.v1
      |
      v
workbook-patch.v1
      |
      + workbook-operation-spec-registry.v1
      v
workbook-target-resolution.v1
      |
      + workbook-coordinate-rule-registry.v1
      v
workbook-coordinate-plan.v1
      |
      + workbook-content-spec-registry.v1
      v
workbook-content-plan.v1
      |
      + workbook-formula-spec-registry.v1
      + workbook-style-spec-registry.v1
      v
workbook-realization-plan.v1
      |
      + workbook-write-context.v1
      v
workbook-write-plan.v1
      |
      + source XLSX hash and size verification
      v
transactional copy-only executor
      |
      +--> executed XLSX
      +--> workbook-execution-receipt.v1
                 |
                 + workbook-input-set.v1
                 v
      reserved-input population boundary
                 |
                 +--> populated XLSX
                 +--> workbook-input-population-receipt.v1
                            |
                            v
      optional spreadsheet calculation engine
                            |
                            v
      immutable-record and cached-result validation
                            |
                            +--> accepted calculated XLSX
                            +--> workbook-calculation-acceptance.v1
```

## Core modules

- `fmr.router`: objective normalization and model selection.
- `fmr.readiness`: required-input comparison.
- `fmr.plan`: ordered, closed-vocabulary transformation plans.
- `fmr.model_specs`: supported model definitions.
- `fmr.workbook.inspect`: deterministic XLSX inspection.
- `fmr.workbook.evidence`: conservative evidence derivation.
- `fmr.workbook.analyse`: model request enrichment and analysis.
- `fmr.workbook.patch`: static patch compilation.
- `fmr.workbook.patch_validation`: patch and receipt validation.
- `fmr.workbook.operation_specs`: versioned operation target policies.
- `fmr.workbook.target_resolution`: semantic target resolution and validation.
- `fmr.workbook.coordinate_rules`: versioned dimensions and allocation policies.
- `fmr.workbook.coordinate_plan`: range allocation, collision checks and validation.
- `fmr.workbook.content_specs`: FMR-owned labels, identifiers and format roles.
- `fmr.workbook.content_plan`: coordinate-bounded symbolic content placement.
- `fmr.workbook.formula_specs`: restricted expression templates and controls.
- `fmr.workbook.style_specs`: palette, protection and number formats.
- `fmr.workbook.realization_plan`: dependency binding, cycle detection and style realization.
- `fmr.workbook.write_plan`: Excel formula compilation and write-record construction.
- `fmr.workbook.write_plan_public`: deterministic public write-plan validation.
- `fmr.workbook.executor`: low-level XLSX application and verification.
- `fmr.workbook.executor_public`: source verification and transactional execution output.
- `fmr.workbook.input_population`: CSV compilation, reserved-input population and value-free receipts.
- `fmr.workbook.input_link`: value-free population-to-calculation hash-chain validation.
- `fmr.workbook.calculation`: engine execution and cached-result inspection.
- `fmr.workbook.calculation_public`: immutable verification and publish-only-on-pass boundary.
- `fmr.contracts`: packaged JSON schemas.

The planning core uses only the Python standard library. Workbook execution, input population and calculated-output validation use the optional `openpyxl` adapter installed through the `executor` extra. Live recalculation requires an external spreadsheet engine; LibreOffice is the first supported adapter.

## Interfaces

```text
CLI ---------+
Python API --+--> deterministic planning and workbook boundaries
HTTP API ----+
Browser UI --HTTP API
                 |
                 +--> optional executor and input population
                 |
                 +--> optional calculation engine
```

The browser sends model-request JSON, XLSX bytes and versioned contracts to the local HTTP API. HTTP handlers contain no financial-model, classification, planning, mutation, input-binding or calculation-acceptance rules of their own.

## Execution boundary

The executor validates the write plan, verifies source identity, rejects unsupported features, applies only accepted records, reopens and verifies the output, publishes atomically and emits a value-free execution receipt. It does not calculate formulas.

## Input-population boundary

Input population:

1. validates and pins the write plan, execution receipt and input set;
2. verifies the selected workbook against the executor output hash and size;
3. rejects external links and unsupported workbook features;
4. verifies every generated record and requires every reserved input to remain blank;
5. writes only numeric or boolean values to `reserve_input` ranges;
6. requests full recalculation;
7. reopens the output and verifies exact inputs and every immutable record;
8. publishes a separate output atomically; and
9. records hashes, counts and identifiers without input values.

`workbook-input-set.v1` is value-bearing. `workbook-input-population-receipt.v1` is deliberately value-free. The link validator proves that a calculation acceptance consumed the exact population output.

## Calculation-acceptance boundary

Calculated-output acceptance validates and pins source contracts, verifies immutable records and populated inputs before and after calculation, opens the output in formula and data-only modes, validates cached results and spreadsheet errors, records only hashes/types/signs/statuses, and publishes workbook bytes only when acceptance passes.
