# Workbook inspection

FMR inspects `.xlsx` files without opening Excel, recalculating formulas or changing the source file.

## Interfaces

```bash
fmr inspect model.xlsx
fmr inspect model.xlsx --output workbook-map.json
```

The local HTTP interface accepts the workbook bytes directly:

```text
POST /api/v1/workbooks/inspect?filename=model.xlsx
```

The browser workbench uses the same endpoint. Uploaded bytes are held only for the request and are not written to disk.

## Output

`workbook-map.v1` records:

- source filename, size and SHA-256 hash;
- sheet names, positions and visibility;
- used ranges;
- formula and hardcoded-value counts;
- merged ranges;
- detected period headers;
- candidate sheet roles with confidence and evidence;
- candidate financial metrics;
- defined names;
- external-link indicators; and
- unsupported workbook features found during inspection.

## Supported input

The current release accepts `.xlsx` only. It rejects legacy binary files, templates, macro-enabled files, encrypted ZIP entries, malformed archives, unsafe archive paths and archives that exceed configured size limits.

## Classification

Sheet and metric classification uses explicit rules. A sheet is returned as `unknown` when no rule matches or when the evidence is ambiguous. The inspector does not invent a role.

## Limits

The inspector does not:

- recalculate formulas;
- execute macros;
- interpret formatting as authoritative financial meaning;
- semantically inspect charts, drawings or pivot tables; or
- modify or save a workbook.
