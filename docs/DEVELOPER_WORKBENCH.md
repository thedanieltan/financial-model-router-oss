# Developer workbench

The developer workbench is a local browser and HTTP interface over the same functions used by the Python package and CLI.

## Start it

Planning only:

```bash
python -m pip install -e ".[dev-ui]"
fmr serve
```

Planning, copied-workbook execution and calculated-output validation:

```bash
python -m pip install -e ".[dev-ui,executor]"
fmr serve
```

Local recalculation also requires LibreOffice with `libreoffice` or `soffice` available. The engine status is displayed in the browser.

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
| GET | `/api/v1/calculation-engine` | report local LibreOffice availability and version |
| POST | `/api/v1/workbooks/calculations` | recalculate and validate a populated executed workbook |
| POST | `/api/v1/workbooks/calculation-acceptances` | validate a workbook recalculated elsewhere |
| POST | `/api/v1/workbooks/calculation-acceptances/validate` | validate a calculation-acceptance receipt |

Execution and calculation requests transport workbook bytes as base64 JSON. The decoded workbook limit is 20 MiB per workbook field. Python and CLI execution should be used for larger files.

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
14. Populate every editable input cell in the downloaded copy.
15. Select the populated copy under **Calculated-output acceptance**.
16. Select **Recalculate and validate**.
17. Download the `-calculated.xlsx` output only when acceptance passes.
18. Review and validate `workbook-calculation-acceptance.v1`.

The synthetic write context is generated only for local testing. It is visible in the editor and never treated as a production binding source.

## Execution behavior

The browser sends the selected source workbook and accepted write plan to the local process. The process:

- verifies the source hash;
- executes in memory;
- reopens and verifies the output;
- returns the output workbook and execution receipt; and
- retains neither file.

The browser immediately downloads the output workbook and displays only the receipt. The selected source file is never modified.

## Calculation behavior

The browser sends the populated executed workbook, write plan and execution receipt to the local process. The process:

- runs LibreOffice headlessly in an isolated temporary profile;
- verifies immutable records before and after calculation;
- confirms every reserved input cell is populated;
- reopens the output in formula and data-only modes;
- checks cached results, result types, sign conventions and spreadsheet errors;
- returns workbook bytes only when acceptance passes; and
- retains neither input nor output.

Failed acceptance displays only the receipt and issue counts. Input and calculated cell values are never included in the receipt.

## Boundary

The interface:

- stores no requests or workbooks;
- enables no cross-origin access;
- applies request-size limits;
- makes no network calls;
- contains no financial-model, workbook-classification, planning, execution or calculation-acceptance rules of its own;
- requires an explicit ready write plan before execution;
- requires a valid execution receipt before calculation; and
- returns no failed calculated workbook.

## Test it

```bash
python -m pip install -e ".[dev-ui,test-ui,executor]"
python -m unittest discover -s tests -v
```

Engine-independent tests generate synthetic XLSX workbooks at runtime. The focused live-acceptance workflow installs LibreOffice and recalculates a runtime-generated workbook. No workbook binaries are committed.
