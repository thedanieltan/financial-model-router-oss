# Developer workbench

The developer workbench is a local browser and HTTP interface over the same functions used by the Python package and CLI.

## Start it

Planning only:

```bash
python -m pip install -e ".[dev-ui]"
fmr serve
```

Planning and copied-workbook execution:

```bash
python -m pip install -e ".[dev-ui,executor]"
fmr serve
```

Defaults:

- address: `127.0.0.1`;
- port: `8000`;
- browser workbench: `/`;
- OpenAPI console: `/docs`;
- ReDoc: `/redoc`.

## HTTP endpoints

The workbench exposes the routing and workbook-planning endpoints plus:

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/workbooks/executions` | apply a ready write plan to a copied workbook |
| POST | `/api/v1/workbooks/execution-receipts/validate` | validate an execution receipt |

The execution request uses `workbook-execution-request.v1` and transports workbook bytes as base64 JSON. The decoded workbook limit is 20 MiB. Python and CLI execution should be used for larger files.

Nothing is retained by the service.

## Browser sequence

1. Select and inspect an `.xlsx` workbook.
2. Edit or load a model request.
3. Analyse the workbook with the request.
4. Compile the analysis into a patch manifest.
5. Resolve patch operations to workbook targets.
6. Enter the explicit number of forecast periods.
7. Plan collision-checked coordinates.
8. Assign labels, placeholders and symbolic identifiers.
9. Bind formula dependencies, style roles, protection and number formats.
10. Review or replace the visible synthetic write context.
11. Compile ordered dry-run write records.
12. Select **Execute copied workbook**.
13. Download the `-fmr.xlsx` output.
14. Review and validate `workbook-execution-receipt.v1`.

The synthetic write context is generated only for local testing. It is visible in the editor and never treated as a production binding source.

## Execution behavior

The browser sends the selected workbook and accepted write plan to the local process. The process:

- verifies the source hash;
- executes in memory;
- reopens and verifies the output;
- returns the output workbook and receipt; and
- retains neither file.

The browser immediately downloads the output workbook and displays only the receipt. The selected source file is never modified.

## Boundary

The interface:

- stores no requests or workbooks;
- enables no cross-origin access;
- applies request-size limits;
- makes no external calls;
- contains no financial-model, workbook-classification, planning or execution rules of its own;
- requires an explicit ready write plan before execution; and
- does not calculate Excel formulas.

## Test it

```bash
python -m pip install -e ".[dev-ui,test-ui,executor]"
python -m unittest discover -s tests -v
```

Tests generate synthetic XLSX archives at runtime. No workbook binaries are committed.
