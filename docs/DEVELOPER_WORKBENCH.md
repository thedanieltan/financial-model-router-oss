# Developer workbench

The developer workbench is a local browser and HTTP interface over the same functions used by the Python package and CLI.

## Start it

Planning and financial-data intake:

```bash
python -m pip install -e ".[dev-ui]"
fmr serve
```

Planning, execution, population and calculated-output validation:

```bash
python -m pip install -e ".[dev-ui,executor]"
fmr serve
```

Local recalculation also requires LibreOffice with `libreoffice` or `soffice` available.

Defaults:

- address: `127.0.0.1`;
- port: `8000`;
- browser workbench: `/`;
- OpenAPI console: `/docs`;
- ReDoc: `/redoc`.

## Financial-data endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/financial-concepts` | return the canonical concept registry |
| POST | `/api/v1/financial-data/packages/from-csv` | normalize a statement CSV |
| POST | `/api/v1/financial-data/mapping-profiles` | create exact account mapping rules |
| POST | `/api/v1/financial-data/mappings` | map package rows to canonical concepts |
| POST | `/api/v1/financial-data/binding-profiles` | create semantic slot bindings |
| POST | `/api/v1/financial-data/binding-plans` | bind concepts or constants to reserved inputs |
| POST | `/api/v1/financial-data/input-sets` | compile a ready plan into `workbook-input-set.v1` |

Validation endpoints are provided for packages, mappings and binding plans.

## Workbook endpoints

The existing endpoints cover copied-workbook execution, input-set validation, reserved-input population, population-to-calculation link validation, spreadsheet calculation and calculated-output acceptance.

Workbook requests transport bytes as base64 JSON. The decoded workbook limit is 20 MiB. Statement CSV is limited to 5 MiB and direct cell-level input CSV to 2 MiB. Nothing is retained by the service.

## Browser sequence

1. Select and inspect an `.xlsx` workbook.
2. Edit or load a model request.
3. Analyse and compile patch, target, coordinate, content, realization and write contracts.
4. Execute the accepted plan on a copied workbook.
5. Under **Financial-data intake**, select a provider-neutral statement CSV.
6. Import it into `financial-data-package.v1`.
7. Review built-in exact mappings and add explicit account-code or account-name rules where needed.
8. Map accounts and review unmapped, ambiguous or invalid rows.
9. Add semantic slot bindings using canonical concepts or explicit constants.
10. Plan bindings and resolve every blocked reserved slot.
11. Compile the ready binding plan into `workbook-input-set.v1`.
12. Populate reserved inputs in the executed copy.
13. Recalculate and validate the populated workbook.
14. Download calculated output only when acceptance passes.

The original cell-level input CSV remains available for developers who already have FMR record IDs. The financial-data workflow removes that requirement by using account concepts and semantic slot IDs.

## Boundary

The interface:

- stores no requests, financial packages or workbooks;
- enables no cross-origin access;
- applies request-size limits;
- makes no outbound network calls;
- contains no mapping, financial-model, planning, execution or calculation rules of its own;
- uses exact account mappings only;
- exposes unresolved rows and slots rather than guessing;
- requires a ready write plan before execution;
- requires a valid execution receipt and complete input set before population;
- writes only reserved input ranges; and
- returns no failed calculated workbook.

## Test it

```bash
python -m pip install -e ".[dev-ui,test-ui,executor]"
python -m unittest discover -s tests -v
```

All financial data and workbooks are synthetic and generated at test runtime. No workbook binaries or third-party templates are committed.
