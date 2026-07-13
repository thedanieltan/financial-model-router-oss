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
source and plan digest pinning
      |
      v
approved additive operation mapping
      |
      v
workbook-patch.v1
      |
      + workbook-operation-spec-registry.v1
      v
deterministic semantic target resolution
      |
      v
workbook-target-resolution.v1
      |
      + workbook-coordinate-rule-registry.v1
      + explicit layout parameters
      v
collision and Excel-bound checks
      |
      v
workbook-coordinate-plan.v1
      |
      + workbook-content-spec-registry.v1
      v
symbolic content slot placement
      |
      v
workbook-content-plan.v1
      |
      v
future formula and style specifications
      |
      v
future executor
      |
      +--> output workbook
      +--> workbook-patch-receipt.v1
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
- `fmr.contracts`: packaged JSON schemas.

The deterministic core uses only the Python standard library.

## Interfaces

```text
CLI ---------+
Python API --+--> deterministic core
HTTP API ----+
Browser UI --HTTP API
```

The browser sends model-request JSON, XLSX bytes and versioned contracts to the local HTTP API. HTTP handlers contain no routing, planning, workbook-classification, patch-mapping, target-resolution, coordinate-allocation or content-placement rules.

## Control boundary

The workbook inspector reads ZIP and XML structures but does not execute formulas, macros or external links. Patch compilation emits additive operation intents without formulas, cells or workbook bytes. Target resolution identifies sheets and placement policies. Coordinate planning reserves collision-checked A1 ranges and sheet positions. Content planning assigns FMR-owned labels and symbolic identifiers inside those ranges, but includes no input values, formula expressions, style definitions or write instructions.

This release does not include the workbook executor. Formula definitions, style definitions, execution, output verification and rollback remain separate acceptance boundaries.
