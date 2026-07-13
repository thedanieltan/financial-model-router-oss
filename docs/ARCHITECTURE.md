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
sheet, period and metric inspection
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
      +--> completed XLSX
      +--> workbook-execution-receipt.v1
                 |
                 + populated reserved inputs
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
- `fmr.workbook.formula_specs`: restricted expression templates, dependencies and formula controls.
- `fmr.workbook.style_specs`: palette, style roles, protection and number formats.
- `fmr.workbook.realization_plan`: dependency binding, cycle detection and style realization.
- `fmr.workbook.write_plan`: Excel formula compilation and dry-run write record construction.
- `fmr.workbook.write_plan_public`: phase normalization and deterministic public validation.
- `fmr.workbook.executor`: low-level XLSX record application and verification.
- `fmr.workbook.executor_public`: source verification, transactional output and receipt construction.
- `fmr.workbook.calculation`: engine discovery, isolated execution, cached-result inspection and acceptance construction.
- `fmr.workbook.calculation_public`: input/output immutable-record verification and publish-only-on-pass boundary.
- `fmr.contracts`: packaged JSON schemas.

The planning core uses only the Python standard library. Workbook execution and calculated-output validation use the optional `openpyxl` adapter installed through the `executor` extra. Live recalculation requires an external spreadsheet engine; LibreOffice is the first supported adapter.

## Interfaces

```text
CLI ---------+
Python API --+--> deterministic planning core
HTTP API ----+
Browser UI --HTTP API
                 |
                 +--> optional executor
                 |
                 +--> optional calculation engine
```

The browser sends model-request JSON, XLSX bytes and versioned contracts to the local HTTP API. HTTP handlers contain no routing, workbook-classification, patch-mapping, target-resolution, coordinate-allocation, content-placement, dependency-binding, style-resolution, write-compilation, workbook-mutation or calculation-acceptance rules.

## Execution boundary

The executor:

1. validates the accepted write plan;
2. verifies the source hash and size;
3. rejects external links and unsupported workbook features;
4. opens the source in memory;
5. applies records only to accepted sheets and coordinates;
6. refuses occupied targets unless the value is already identical;
7. saves and reopens the output;
8. verifies every record;
9. writes a temporary output and publishes it atomically; and
10. emits a content-free receipt using before and after state hashes.

The executor does not calculate Excel formulas. It marks the output for full recalculation.

## Calculation-acceptance boundary

Calculated-output acceptance:

1. validates and pins the write plan and execution receipt;
2. permits user edits only inside reserved input ranges;
3. verifies immutable records before the spreadsheet engine runs;
4. runs LibreOffice in a temporary directory and isolated profile, or accepts an externally recalculated workbook;
5. verifies immutable records and populated inputs after calculation;
6. opens the output in formula and data-only modes;
7. validates cached results, declared output types, sign conventions and formula errors;
8. scans every formula cell for missing caches or spreadsheet error tokens;
9. records only hashes, identifiers, types, signs and issue codes; and
10. publishes workbook bytes only when acceptance passes.
