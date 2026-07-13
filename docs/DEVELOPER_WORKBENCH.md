# Developer workbench

The developer workbench is a local browser and HTTP interface over the same functions used by the Python package and CLI.

## Start it

```bash
python -m pip install -e ".[dev-ui]"
fmr serve
```

Defaults:

- address: `127.0.0.1`;
- port: `8000`;
- browser workbench: `/`;
- OpenAPI console: `/docs`;
- ReDoc: `/redoc`.

## HTTP endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | service and version check |
| GET | `/api/v1/model-families` | list supported model definitions |
| GET | `/api/v1/workbook-operation-specs` | return the versioned operation registry |
| GET | `/api/v1/workbook-coordinate-rules` | return the versioned coordinate-rule registry |
| GET | `/api/v1/workbook-content-specs` | return the versioned content-specification registry |
| GET | `/api/v1/fixtures` | list bundled synthetic requests |
| GET | `/api/v1/fixtures/{fixture_id}` | load one fixture |
| POST | `/api/v1/route` | route a model request |
| POST | `/api/v1/plan` | build a transformation plan |
| POST | `/api/v1/validate-plan` | validate a plan payload |
| POST | `/api/v1/workbooks/inspect?filename=...` | inspect an XLSX workbook |
| POST | `/api/v1/workbooks/analyse` | combine a workbook map and model request |
| POST | `/api/v1/workbooks/patches` | compile `workbook-analysis.v1` into a patch manifest |
| POST | `/api/v1/workbooks/patches/validate` | validate a patch manifest |
| POST | `/api/v1/workbooks/patch-receipts/validate` | validate a receipt, optionally against its patch |
| POST | `/api/v1/workbooks/target-resolutions` | resolve patch operations to semantic workbook targets |
| POST | `/api/v1/workbooks/target-resolutions/validate` | recompute and validate a target resolution |
| POST | `/api/v1/workbooks/coordinate-plans` | reserve deterministic sheet positions and A1 ranges |
| POST | `/api/v1/workbooks/coordinate-plans/validate` | recompute and validate a coordinate plan |
| POST | `/api/v1/workbooks/content-plans` | assign symbolic content slots to reserved ranges |
| POST | `/api/v1/workbooks/content-plans/validate` | recompute and validate a content plan |

The inspection endpoint accepts raw workbook bytes rather than multipart form data. The remaining workbook endpoints accept JSON contracts. Nothing is retained.

## Browser sequence

1. Select and inspect an `.xlsx` workbook.
2. Edit or load a model request.
3. Analyse the workbook with the request.
4. Compile the resulting analysis into a patch manifest.
5. Resolve every patch operation to an existing, new, planned, set or blocked target.
6. Enter the explicit number of forecast periods.
7. Plan collision-checked coordinates.
8. Assign labels, placeholders and symbolic identifiers to the reserved ranges.
9. Validate or copy the JSON.

The browser does not execute the patch or write to the workbook.

## Boundary

The interface:

- stores no requests or workbooks;
- enables no cross-origin access;
- applies separate JSON and workbook request-size limits;
- makes no external calls;
- contains no financial-model, workbook-classification, patch-mapping, target-resolution, coordinate-allocation or content-placement rules of its own; and
- exposes no workbook executor.

## Test it

```bash
python -m pip install -e ".[dev-ui,test-ui]"
python -m unittest discover -s tests -v
```

Tests generate synthetic XLSX archives at runtime. No workbook binaries are committed.
