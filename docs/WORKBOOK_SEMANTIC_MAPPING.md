# Workbook semantic mapping

FMR treats an existing spreadsheet as the user's working financial model. Before any formula can be written, FMR must understand the workbook without modifying it.

`workbook-map.v1` remains the structural inspection contract. `workbook-semantic-map.v1` layers financial meaning and formula lineage on top without breaking existing consumers.

## Command

```bash
fmr semantic-map model.xlsx --output semantic-map.json
```

The command is read-only. The source workbook hash is verified before and after file-based mapping.

## What the semantic map contains

For each worksheet FMR records:

- candidate financial role and confidence;
- recognized annual, monthly or quarterly period columns;
- whether a period is explicitly actual, budget, forecast or otherwise unspecified;
- recognized financial metric rows and their source coordinates;
- the coordinates and cell kind of each metric/period intersection;
- explicit textual currency and scale evidence;
- formula hashes and direct A1/range references;
- cross-sheet formula dependencies.

The semantic map deliberately does **not** contain financial numeric cell values or raw formulas. It identifies where governed facts and calculations live so later work packages can construct auditable formula plans.

## Conservative inference

FMR does not guess when the workbook is ambiguous.

- Unmarked periods remain `unspecified`.
- Unknown row labels remain `unknown`.
- Bare `$` and `¥` symbols are not sufficient to assert a currency.
- Scale is inferred only from explicit text such as `in thousands` or `USD millions`.
- Formula lineage currently records direct Excel A1/range references; it does not claim to understand every Excel function or dynamic-reference construct.

These boundaries are intentional. A wrong semantic map can cause a correct formula to be written to the wrong financial concept, so ambiguity must be surfaced before mutation is allowed.

## Relationship to formula execution

The intended lifecycle is:

```text
Existing XLSX
  ↓
workbook-map.v1
  ↓
workbook-semantic-map.v1
  ↓
user request + FMR router
  ↓
analyst workflow
  ↓
formula/write plan
  ↓
transactional workbook copy
  ↓
spreadsheet recalculation
  ↓
financial validation
  ↓
meeting-ready workbook
  ↓
agent commentary / follow-up
```

WP-FMR-WBM-35 stops at the semantic-map boundary. Formula writing and workbook mutation remain separate acceptance gates.
