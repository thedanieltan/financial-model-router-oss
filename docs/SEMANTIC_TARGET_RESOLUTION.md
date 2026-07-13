# Semantic target resolution

FMR resolves each `workbook-patch.v1` operation against the inspected workbook before any executor is introduced.

## Purpose

A patch operation names a semantic target such as `assumptions`, `forecast_periods`, `debt_schedule` or `valuation`. The resolver determines whether that target refers to:

- one existing sheet;
- a set of existing sheets;
- a new canonical sheet;
- a sheet already planned by an earlier operation; or
- an unresolved or ambiguous target.

It does not produce cell writes or formulas.

## Operation specifications

`workbook-operation-spec-registry.v1` contains one versioned specification for every approved transformation operation. Each specification records:

- the operation and semantic role;
- accepted classified sheet roles;
- deterministic sheet-name aliases;
- optional metric evidence;
- target cardinality;
- the canonical fallback sheet name;
- placement relative to the existing used range; and
- whether a new sheet may be planned.

The registry is hashed. `workbook-target-resolution.v1` pins that hash.

## Resolution rules

Existing workbook evidence takes precedence over a new target.

A single target is reused only when there is one highest-confidence match. Equal-confidence matches are blocked as ambiguous.

Sheet-set operations resolve all qualifying sheets in workbook order. Operations that link the three financial statements require one classified income statement, balance sheet and cash-flow statement.

When an operation plans a new sheet, later operations may resolve to that planned sheet. For example, the first valuation operation can plan `Valuation`; later valuation sections reuse that planned target.

## Output

Each operation resolution records:

- its operation and specification reference;
- status and confidence;
- sheet names;
- existing-sheet anchors, including position, visibility and used range;
- placement policy;
- evidence; and
- blockers.

The output is deterministic and can be checked against the original analysis and patch.

## Interfaces

```bash
fmr operation-specs --output operation-specs.json
fmr resolve-targets workbook-analysis.json workbook-patch.json \
  --output target-resolution.json
fmr validate-target-resolution target-resolution.json \
  --analysis workbook-analysis.json \
  --patch workbook-patch.json
```

HTTP:

```text
GET  /api/v1/workbook-operation-specs
POST /api/v1/workbooks/target-resolutions
POST /api/v1/workbooks/target-resolutions/validate
```

## Boundary

Target resolution does not:

- modify a workbook;
- assign exact write coordinates;
- generate formulas;
- execute macros or external links; or
- claim that an executor is available.

`ready_for_executor` means that the patch and all semantic targets are internally resolved. `execution_supported_by_this_release` remains `false`.
