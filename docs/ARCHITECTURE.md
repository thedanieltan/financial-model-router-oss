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
- `fmr.workbook.patch`: static patch compilation and receipt validation.
- `fmr.contracts`: packaged JSON schemas.

The deterministic core uses only the Python standard library.

## Interfaces

```text
CLI ---------+
Python API --+--> deterministic core
HTTP API ----+
Browser UI --HTTP API
```

The browser sends model-request JSON, XLSX bytes and versioned contracts to the local HTTP API. HTTP handlers contain no routing, planning, workbook-classification or patch-mapping rules.

## Control boundary

The workbook inspector reads ZIP and XML structures but does not execute formulas, macros or external links. Patch compilation emits additive operation intents without formulas, cells or workbook bytes. This release does not include the workbook executor. Execution, output verification and rollback remain a separate acceptance boundary.
