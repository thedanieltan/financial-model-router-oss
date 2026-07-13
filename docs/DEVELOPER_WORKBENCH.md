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
| GET | `/api/v1/fixtures` | list bundled synthetic requests |
| GET | `/api/v1/fixtures/{fixture_id}` | load one fixture |
| POST | `/api/v1/route` | route a model request |
| POST | `/api/v1/plan` | build a transformation plan |
| POST | `/api/v1/validate-plan` | validate a plan payload |
| POST | `/api/v1/workbooks/inspect?filename=...` | inspect an XLSX workbook |

The workbook endpoint accepts raw request bytes rather than multipart form data. This keeps the optional interface small and avoids retaining temporary files.

## Boundary

The interface:

- stores no requests or workbooks;
- enables no cross-origin access;
- applies separate JSON and workbook request-size limits;
- makes no external calls; and
- contains no financial-model or workbook-classification logic of its own.

## Test it

```bash
python -m pip install -e ".[dev-ui,test-ui]"
python -m unittest discover -s tests -v
```

Tests generate synthetic XLSX archives at runtime. No workbook binaries are committed.
