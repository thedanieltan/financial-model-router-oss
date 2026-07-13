# Developer workbench

The developer workbench is a local browser and HTTP interface over the same functions used by the Python package and CLI.

## Start it

Planning only:

```bash
python -m pip install -e ".[dev-ui]"
fmr serve
```

Planning, execution, input population and calculated-output validation:

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
| POST | `/api/v1/workbooks/input-sets/from-csv` | compile explicit CSV cells into `workbook-input-set.v1` |
| POST | `/api/v1/workbooks/input-sets/validate` | validate an input set |
| POST | `/api/v1/workbooks/input-populations` | populate reserved input ranges in the executed copy |
| POST | `/api/v1/workbooks/input-population-receipts/validate` | validate a value-free population receipt |
| POST | `/api/v1/workbooks/input-population-receipts/validate-calculation-link` | validate the population-to-calculation hash chain |
| GET | `/api/v1/calculation-engine` | report local LibreOffice availability and version |
| POST | `/api/v1/workbooks/calculations` | recalculate and validate a populated workbook |
| POST | `/api/v1/workbooks/calculation-acceptances` | validate a workbook recalculated elsewhere |
| POST | `/api/v1/workbooks/calculation-acceptances/validate` | validate a calculation-acceptance receipt |

Workbook requests transport bytes as base64 JSON. The decoded workbook limit is 20 MiB. CSV input is limited to 2 MiB. Python and CLI workflows should be used for larger files.

Nothing is retained by the service.

## Browser sequence

1. Select and inspect an `.xlsx` workbook.
2. Edit or load a model request.
3. Analyse the workbook and compile patch, target, coordinate, content, realization and write contracts.
4. Review the visible write context and compile ordered dry-run writes.
5. Select **Execute copied workbook**.
6. Download the `-fmr.xlsx` output and review the execution receipt.
7. Select a UTF-8 CSV under **Governed input population**.
8. Select **Compile input CSV** to produce a pinned input-set document.
9. Review or replace the visible `workbook-input-set.v1` JSON.
10. Select **Populate reserved inputs**.
11. Download the `-populated.xlsx` output and review the value-free population receipt.
12. Select **Recalculate and validate**. The governed populated copy is used automatically unless another workbook is selected.
13. FMR verifies the population-to-calculation hash chain.
14. Download the calculated workbook only when acceptance passes.

The CSV must provide one row per reserved cell using `record_id,cell_index,value_type,value,source_ref`. Only finite numbers and booleans are accepted.

## Input-population behavior

The browser sends the executed workbook, input set, write plan and execution receipt to the local process. The process verifies the executor output hash, proves generated records are unchanged, writes only reserved input cells, reopens and verifies the output, returns a separate workbook plus a value-free receipt, and retains neither artifact.

Input-set JSON contains the values required for workbook population. Population receipts contain no input values. The selected source is never modified.

## Calculation behavior

The browser sends the populated workbook, write plan and execution receipt to the local process. The process runs LibreOffice headlessly, verifies immutable records and populated inputs, checks cached results and errors, and returns workbook bytes only when acceptance passes.

Failed acceptance displays only the receipt and issue counts. Input and calculated values are not included in receipts.

## Boundary

The interface:

- stores no requests or workbooks;
- enables no cross-origin access;
- applies request-size limits;
- makes no outbound network calls;
- contains no financial-model, planning, execution, input-binding or calculation rules of its own;
- requires a ready write plan before execution;
- requires a valid execution receipt and complete input set before population;
- writes only reserved input ranges; and
- returns no failed calculated workbook.

## Test it

```bash
python -m pip install -e ".[dev-ui,test-ui,executor]"
python -m unittest discover -s tests -v
```

All workbooks are generated at test runtime. The live calculation workflow installs LibreOffice and recalculates a synthetic workbook. No workbook binaries are committed.
