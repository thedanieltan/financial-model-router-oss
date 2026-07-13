# Calculated-output acceptance

FMR 0.4.1 adds an explicit acceptance gate after transactional workbook execution.

The 0.4 executor writes formulas and requests workbook recalculation, but it does not calculate formula results itself. Calculated-output acceptance runs an optional spreadsheet engine or validates a workbook recalculated elsewhere, then checks cached formula results before publishing the output.

## Sequence

```text
workbook-write-plan.v1
        |
        v
copy-only XLSX execution
        |
        v
workbook-execution-receipt.v1
        |
        + populated editable input cells
        v
spreadsheet calculation engine
        |
        v
workbook-calculation-acceptance.v1
```

## Supported calculation paths

### Local LibreOffice engine

Install LibreOffice and run:

```bash
fmr calculation-engine-status

fmr calculate-output populated.xlsx write-plan.json execution-receipt.json \
  --output calculated.xlsx \
  --receipt calculation-acceptance.json
```

FMR discovers `libreoffice` or `soffice`. `FMR_CALCULATION_ENGINE` or `--engine` may point to a specific executable.

The adapter runs headlessly with:

- a temporary source directory;
- a separate temporary output directory;
- an isolated temporary LibreOffice user profile;
- a bounded timeout;
- hashed standard output and standard error rather than captured text in the receipt; and
- publication only after acceptance passes.

### External spreadsheet engine

A workbook recalculated in Excel, LibreOffice or another compatible engine can be validated without invoking that engine from FMR:

```bash
fmr accept-calculated-output populated.xlsx calculated.xlsx \
  write-plan.json execution-receipt.json \
  --receipt calculation-acceptance.json \
  --engine-name "Microsoft Excel" \
  --engine-version "declared-by-caller"
```

This path trusts only the declared engine identity. It does not trust the workbook contents: the same immutable-record, formula-cache and error checks still run.

## Acceptance checks

A calculated workbook passes only when:

- the write plan and execution receipt are valid and hash-pinned;
- the populated input workbook preserves all generated labels, formulas, styles, protection and sheet setup;
- every reserved input cell is populated;
- the calculation output preserves the same immutable records and input values;
- every planned formula still exists;
- every planned formula has a cached result;
- cached result types match declared formula output types;
- positive sign conventions are not violated;
- no formula result is an Excel error token;
- no formula anywhere in the workbook lacks a cached result;
- neither input nor output contains external links; and
- unsupported charts, pivots, drawings or sheet types are absent.

Input edits are allowed only inside `reserve_input` ranges. A populated workbook may therefore have a different SHA-256 hash from the immediate executor output while still passing immutable-record verification.

## Receipt privacy

`workbook-calculation-acceptance.v1` contains:

- source and output file hashes and sizes;
- engine identity and adapter metadata;
- record identifiers and issue codes;
- formula identifiers, coordinates, observed data types and signs; and
- aggregate counts.

It does **not** contain:

- input values;
- calculated values;
- cached formula values;
- workbook cell contents;
- engine standard output or standard error text; or
- workbook bytes.

## Publication and failure behavior

The file command writes to a new output path only when acceptance status is `passed`.

- The populated input workbook is never overwritten.
- Existing output files are rejected.
- Failed acceptance returns a receipt but does not publish the calculated workbook.
- Temporary output is removed if atomic publication fails.
- The HTTP and browser interfaces return workbook bytes only for passed acceptance.

## Formula semantics

FMR validates cached results but does not claim semantic correctness beyond its declared formula specifications, type checks, sign conventions and error detection. Spreadsheet-engine behavior and financial-model review remain separate acceptance responsibilities.
