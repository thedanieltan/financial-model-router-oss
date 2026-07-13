# Workbook execution

FMR 0.4 applies an accepted `workbook-write-plan.v1` to a copied `.xlsx` workbook.

Execution is explicit. Planning commands remain non-mutating.

## Install

```bash
python -m pip install -e ".[executor]"
```

For the browser workbench:

```bash
python -m pip install -e ".[dev-ui,executor]"
fmr serve
```

## CLI

```bash
fmr execute-writes source.xlsx write-plan.json \
  --output completed.xlsx \
  --receipt execution-receipt.json

fmr validate-execution-receipt execution-receipt.json \
  --write-plan write-plan.json
```

The command refuses to:

- use the source path as the output path;
- overwrite an existing output;
- accept a source whose hash or size differs from the write plan;
- execute a blocked or malformed write plan;
- write to occupied cells unless the existing value is already identical;
- execute workbooks with external links or unsupported features; or
- leave a partial output after a publication failure.

## Execution sequence

1. Validate `workbook-write-plan.v1`.
2. Verify the source SHA-256 and byte size.
3. Reinspect the source workbook.
4. Load the workbook without external-link preservation.
5. Apply the accepted phases in order:
   - sheet setup;
   - labels and input reservations;
   - formulas and validations;
   - styles, number formats and cell protection.
6. Request full recalculation when Excel next opens the workbook.
7. Save the output in memory.
8. Reinspect and reopen the output.
9. Verify every accepted write record.
10. Atomically publish the output file.
11. Emit `workbook-execution-receipt.v1`.

FMR does not calculate Excel formulas. The receipt records `formula_calculation_deferred: true`.

## Receipt

The receipt includes:

- execution, write-plan and file hashes;
- output filename and size;
- one applied record for every accepted write record;
- before and after state hashes;
- cell counts;
- reopened-output verification; and
- source-preservation controls.

It does not include cell values, formulas, workbook bytes or proprietary workbook content.

## Python

```python
from fmr import execute_workbook_write_plan_file

receipt = execute_workbook_write_plan_file(
    "source.xlsx",
    output_path="completed.xlsx",
    write_plan=write_plan,
)
```

An in-memory interface is also available:

```python
from fmr import execute_workbook_write_plan_bytes

result = execute_workbook_write_plan_bytes(
    source_bytes,
    filename="source.xlsx",
    output_filename="completed.xlsx",
    write_plan=write_plan,
)

output_bytes = result.output_bytes
receipt = result.receipt
```

## Local API

```text
POST /api/v1/workbooks/executions
POST /api/v1/workbooks/execution-receipts/validate
```

The local execution endpoint transports workbook bytes as base64 JSON. The decoded workbook limit is 20 MiB. The returned workbook is downloaded by the browser and is not retained by the service.

For larger files, use the Python or CLI interface.

## Browser

The workbench enables **Execute copied workbook** only when:

- the selected workbook remains available in the browser;
- a write plan has been compiled; and
- `ready_for_executor` is true.

The downloaded filename receives the `-fmr.xlsx` suffix. The result panel displays the receipt, not workbook bytes.

## Remaining boundary

The current executor does not:

- calculate formula results;
- evaluate whether forecast assumptions are commercially reasonable;
- support `.xls`, `.xlsm`, `.xlsb` or template formats;
- preserve macros or external links;
- overwrite source or output files;
- use third-party workbook templates; or
- hide synthetic browser bindings from the developer.
