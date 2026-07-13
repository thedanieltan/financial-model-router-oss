# Governed workbook input population

FMR 0.4.2 fills the editable ranges created by the transactional workbook executor without permitting arbitrary workbook edits.

## Contracts

`workbook-input-set.v1` is the controlled value-bearing input document. It pins:

- the accepted `workbook-write-plan.v1`;
- the corresponding `workbook-execution-receipt.v1`;
- the declared source and optional source-file hash;
- every reserved input record in write-plan order; and
- a numeric or boolean value for every cell in each reserved range.

`workbook-input-population-receipt.v1` is the value-free audit document. It contains file hashes, source-contract hashes, record identifiers, range coordinates, counts, source-reference hashes and before/after state hashes. It never contains input values or workbook bytes.

## CSV input

The CSV compiler accepts UTF-8 with exactly these columns:

```text
record_id,cell_index,value_type,value,source_ref
```

Each row represents one cell in a `reserve_input` record. `cell_index` starts at 1 within each record. Every reserved record and every cell must be supplied exactly once.

Allowed value types are:

- `number`: a finite integer or decimal;
- `boolean`: `true` or `false`.

Text, formulas, blank values, NaN and infinity are rejected.

## CLI

```bash
fmr compile-input-set-csv inputs.csv write-plan.json execution-receipt.json \
  --output input-set.json

fmr validate-input-set input-set.json \
  --write-plan write-plan.json \
  --execution-receipt execution-receipt.json

fmr populate-inputs executed.xlsx input-set.json \
  write-plan.json execution-receipt.json \
  --output populated.xlsx \
  --receipt population-receipt.json

fmr validate-input-population-receipt population-receipt.json \
  --input-set input-set.json \
  --write-plan write-plan.json \
  --execution-receipt execution-receipt.json
```

After calculation:

```bash
fmr validate-input-calculation-link \
  population-receipt.json calculation-acceptance.json
```

The link validator proves that the calculated workbook input hash and size match the governed population output and that both artifacts pin the same write plan and execution receipt.

## HTTP API

```text
POST /api/v1/workbooks/input-sets/from-csv
POST /api/v1/workbooks/input-sets/validate
POST /api/v1/workbooks/input-populations
POST /api/v1/workbooks/input-population-receipts/validate
POST /api/v1/workbooks/input-population-receipts/validate-calculation-link
```

Workbook and CSV bytes are transported as base64 JSON and retained only for the duration of the request.

## Safety boundary

Population:

1. validates the write plan, execution receipt and input set;
2. verifies the selected workbook hash and size against the executor output;
3. rejects external links and unsupported workbook features;
4. proves all generated workbook records remain unchanged and all reserved inputs remain blank;
5. writes only cells governed by `reserve_input` records;
6. requests spreadsheet recalculation;
7. saves and reopens the output;
8. verifies exact populated values and every immutable record; and
9. atomically publishes a new workbook path.

It refuses source overwrite, existing output paths, incomplete input coverage, unknown record IDs, shape mismatches and non-finite values.

## Privacy and provenance

Input sets contain the values required to populate the workbook and should be handled as sensitive working artifacts. Population receipts deliberately exclude those values. `source_ref` is hashed in the receipt so provenance can be compared without reproducing source descriptions.

FMR stores neither artifact and makes no outbound network calls.
