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
```

## Core modules

- `fmr.router`: objective normalization and model selection.
- `fmr.readiness`: required-input comparison.
- `fmr.plan`: ordered, closed-vocabulary transformation plans.
- `fmr.model_specs`: supported model definitions.
- `fmr.workbook`: deterministic XLSX inspection and workbook-map types.
- `fmr.contracts`: packaged JSON schemas.

The deterministic core uses only the Python standard library.

## Interfaces

```text
CLI ---------+
Python API --+--> deterministic core
HTTP API ----+
Browser UI --HTTP API
```

The browser sends model-request JSON or XLSX bytes to the local HTTP API. HTTP handlers contain no routing, planning or workbook-classification rules.

## Control boundary

The workbook inspector reads ZIP and XML structures but does not execute formulas, macros or external links. The planner emits approved operation names only. Workbook mutation remains a separate layer with preconditions, rollback and output verification.
