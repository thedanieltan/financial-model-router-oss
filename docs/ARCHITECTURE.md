# Architecture

## Architecture status

FMR `1.0.0-alpha` implements and hardens the local provider-router architecture
defined in [PRODUCT_CHARTER.md](PRODUCT_CHARTER.md). It is not a production 1.0
release. The diagram and modules below also
document the operational pre-1.0 workbook compatibility path. See
[CODE_INVENTORY.md](CODE_INVENTORY.md) for its disposition.

The target repository boundary is:

```text
fmr/
├── core/                 # jobs, families, routing, policies, handoffs, receipts
├── registry/             # provider and package manifest discovery
├── data/                 # canonical concepts and data packages
├── adapters/sources/     # external source -> canonical data
├── providers/native_xlsx/# workbook-specific implementation
├── sdk/                  # third-party provider extension surface
└── contracts/            # provider-neutral and compatibility schemas
```

Routing and discovery do not import or execute provider implementations.
Configured directories contribute manifests without code execution. Installed
adapter and executor entry points load only after selection and complete handoff
verification. Native XLSX can be disabled without invalidating a non-XLSX route.

## Current compatibility architecture

```text
statement CSV
      |
      v
financial-data-package.v1
      |
      + financial-concept-registry.v1
      + financial-data-mapping-profile.v1
      v
financial-data-mapping-result.v1
      |
      + financial-data-binding-profile.v1
      + workbook-write-plan.v1
      + workbook-execution-receipt.v1
      v
workbook-input-binding-plan.v1
      |
      v
workbook-input-set.v1

model-request.v1
      |
      v
objective normalization
      |
      v
model definition registry
      |
      +--> recommendation
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

Financial-data intake:

- `fmr.financial_data.common`: concept registry, identifiers and shared controls.
- `fmr.financial_data.package`: provider-neutral statement CSV normalization.
- `fmr.financial_data.mapping`: exact alias and explicit mapping-profile resolution.
- `fmr.financial_data.binding`: semantic slot binding and governed input-set compilation.

Routing and planning:

- `fmr.router`: objective normalization and model selection.
- `fmr.readiness`: required-input comparison.
- `fmr.plan`: ordered, closed-vocabulary transformation plans.
- `fmr.model_specs`: supported model definitions.

Workbook lifecycle:

- `fmr.workbook.inspect`: deterministic XLSX inspection.
- `fmr.workbook.evidence`: conservative evidence derivation.
- `fmr.workbook.analyse`: request enrichment and analysis.
- `fmr.workbook.patch` and `patch_validation`: patch compilation and validation.
- `fmr.workbook.operation_specs` and `target_resolution`: semantic target policies.
- `fmr.workbook.coordinate_rules` and `coordinate_plan`: collision-checked allocation.
- `fmr.workbook.content_specs` and `content_plan`: symbolic workbook content.
- `fmr.workbook.formula_specs`, `style_specs` and `realization_plan`: governed formula and style realization.
- `fmr.workbook.write_plan`: Excel formula compilation and ordered write records.
- `fmr.workbook.executor` and `executor_public`: copy-only XLSX execution.
- `fmr.workbook.input_population`: reserved-input population and value-free receipts.
- `fmr.workbook.input_link`: population-to-calculation hash-chain validation.
- `fmr.workbook.calculation` and `calculation_public`: spreadsheet-engine execution and calculated-output acceptance.
- `fmr.contracts`: packaged JSON schemas.

The routing, planning and financial-data intake core uses only the Python standard library. Workbook execution, population and calculated-output validation use the optional `openpyxl` adapter. Live recalculation requires an external spreadsheet engine; LibreOffice is the first supported adapter.

## Interfaces

```text
CLI ---------+
Python API --+--> deterministic intake, planning and workbook boundaries
HTTP API ----+
Browser UI --HTTP API
                 |
                 +--> optional executor and input population
                 +--> optional calculation engine
```

HTTP handlers translate versioned requests and responses only. They contain no mapping, financial-model, planning, mutation or acceptance rules.

## Financial-data boundary

The first adapter accepts one entity and currency per UTF-8 statement CSV. It retains source values as decimal strings, applies exact aliases or explicit overrides, keeps unmapped rows visible and binds concepts or constants to semantic workbook slot IDs. It does not perform fuzzy matching, currency conversion, consolidation or assumption inference.

A governed input set is emitted only when every reserved numeric or boolean slot is covered and the write plan and execution receipt hashes match.

## Execution boundary

The executor verifies source identity, rejects unsupported features, applies only accepted records, reopens and verifies the output, publishes atomically and emits a value-free receipt. It does not calculate formulas.

## Input-population boundary

Input population validates and pins its contracts, verifies the executor output, proves generated records remain unchanged, writes only numeric or boolean values to reserved ranges, reopens the output, publishes a separate copy and records hashes and counts without input values.

## Calculation-acceptance boundary

Calculated-output acceptance verifies immutable records and populated inputs before and after calculation, opens the output in formula and data-only modes, validates cached results and spreadsheet errors, records only hashes, types, signs and statuses, and publishes workbook bytes only when acceptance passes.
