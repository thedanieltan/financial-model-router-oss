# Formula and style specifications

Version `0.3.4` resolves the symbolic identifiers in `workbook-content-plan.v1` into deterministic formula dependencies and declarative presentation rules.

It does not generate Excel formulas or edit workbooks.

## Contracts

The work package publishes:

- `workbook-formula-spec-registry.v1`;
- `workbook-style-spec-registry.v1`;
- `workbook-realization-plan-request.v1`; and
- `workbook-realization-plan.v1`.

Every realization plan pins the source content plan and both registries by SHA-256.

## Formula language

Formula and validation specifications use `fmr-expression.v1`, a restricted expression language owned by FMR.

Example:

```text
MUL({{volume_driver}}, {{price_driver}}, ADD(1, {{growth_rate}}))
```

The expression template names declared dependencies. It is not an Excel formula and cannot be written to a workbook directly.

A formula specification records:

- a stable identifier;
- formula kind;
- expression template;
- declared dependencies;
- output type;
- sign convention;
- fill policy; and
- circularity policy.

Raw A1 coordinates, sheet references, external-workbook references and volatile functions are rejected from the registry.

## Dependency sources

A dependency is one of:

- `content_slot` — another input or calculated content slot;
- `period_context` — period index or prior-period formula supplied later;
- `source_workbook` — existing workbook evidence resolved later;
- `reference_target` — a previously accepted semantic workbook target; or
- `validation_context` — deterministic inputs to a validation rule.

Content-slot dependencies are resolved conservatively. FMR first looks inside the same allocation, sheet and operation, then the same operation, then the global plan. Missing or ambiguous required bindings block the realization plan.

The resulting dependency graph is checked for cycles.

## Style registry

The style registry is separate from financial-model logic. It contains:

- an original FMR palette;
- role-based font, fill, alignment and border rules;
- cell-protection rules;
- semantic number formats; and
- semantic types for input identifiers.

Input slots are unlocked. Calculated outputs and controls are locked.

The registry uses the Aptos font and a small neutral palette. It contains no copied workbook theme or third-party template styling.

## Realization plan

`workbook-realization-plan.v1` preserves each content slot and adds:

- resolved formula specification reference;
- expression template and dependency bindings;
- output type and sign convention;
- style specification reference;
- number-format specification reference;
- resolved protection state; and
- operation-level blockers.

Reference-only slots remain coordinate-free.

## Interfaces

```bash
fmr formula-specs --output formula-specs.json
fmr style-specs --output style-specs.json
fmr plan-realization content-plan.json --output realization-plan.json
fmr validate-realization-plan realization-plan.json \
  --content-plan content-plan.json
```

```text
GET  /api/v1/workbook-formula-specs
GET  /api/v1/workbook-style-specs
POST /api/v1/workbooks/realization-plans
POST /api/v1/workbooks/realization-plans/validate
```

## Boundary

This release does not include:

- Excel formula strings;
- resolved A1 references inside formulas;
- cell values;
- write ordering;
- merged-cell instructions;
- workbook serialization;
- workbook mutation; or
- recalculation.

Those belong to a separate write-plan compiler and executor acceptance boundary.
