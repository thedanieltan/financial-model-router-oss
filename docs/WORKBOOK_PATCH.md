# Workbook patch contract

`workbook-patch.v1` is a static manifest for a future workbook executor. It does not edit a workbook.

## Compile a patch

```bash
fmr compile-patch workbook-analysis.json --output workbook-patch.json
fmr validate-patch workbook-patch.json
```

The input must be an untampered `workbook-analysis.v1` document. FMR recomputes the analysis before compiling the patch.

## What the patch contains

A patch records:

- the source filename, size and SHA-256 hash;
- SHA-256 digests of the workbook analysis and transformation plan;
- the selected model family;
- blockers that prevent the manifest from being handed to an executor;
- source and contract preconditions;
- ordered, additive operation intents;
- a reverse-order rollback plan;
- required output checks; and
- controls that an executor must enforce.

Patch IDs are derived from the canonical patch payload. Changing the source hash, an operation or a validation rule invalidates the ID.

## Operation boundary

Operations use a closed vocabulary:

- `ensure_sheet`;
- `ensure_section`;
- `append_periods`;
- `link_components`;
- `add_control`;
- `add_scenario`; and
- `add_sensitivity`.

Each operation points to an FMR-owned operation specification. Patch documents cannot contain formulas, cell coordinates, workbook bytes, macros or scripts.

`ready_for_executor` means the manifest has no model-readiness, external-link or operation-mapping blockers. It does not mean this release can execute the patch. `execution_supported_by_this_release` remains `false` until the workbook executor is implemented and accepted separately.

## Rollback records

Each operation requires an execution receipt containing:

- the operation ID;
- the before-state hash;
- the after-state hash;
- affected XLSX package parts; and
- an optional rollback-state hash.

Executors must emit `workbook-patch-receipt.v1`. The patch rollback plan references operation receipts in reverse application order.

```bash
fmr validate-patch-receipt receipt.json --patch workbook-patch.json
```

Receipt validation checks the patch ID, source hash and operation IDs when the related patch is supplied.

## HTTP endpoints

```text
POST /api/v1/workbooks/patches
POST /api/v1/workbooks/patches/validate
POST /api/v1/workbooks/patch-receipts/validate
```

The first endpoint accepts `workbook-analysis.v1` and returns `workbook-patch.v1`.

## Current limit

FMR does not yet:

- copy a workbook;
- resolve exact target cells;
- insert formulas;
- apply patch operations;
- create execution receipts; or
- roll back an output workbook.

Those functions belong to the later workbook-executor work package.
