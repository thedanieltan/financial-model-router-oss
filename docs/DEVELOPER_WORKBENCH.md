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

For container testing, expose the server explicitly:

```bash
fmr serve --host 0.0.0.0 --port 8000
```

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

## Boundary

The interface:

- does not store requests;
- does not accept workbook uploads;
- does not enable cross-origin access;
- rejects declared request bodies above 1 MiB;
- does not call external services; and
- contains no financial-model logic of its own.

The HTTP handlers translate request payloads into `ModelRequest` objects and call the existing router, readiness and planning modules.

## Test it

```bash
python -m pip install -e ".[dev-ui,test-ui]"
python -m unittest discover -s tests -v
```

The API tests verify exact JSON parity between the Python and HTTP interfaces for the bundled fixtures.
