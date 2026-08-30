# Dry-run monthly FP&A formula planning

`fmr formula-plan <workbook.xlsx>` consumes the accepted `workbook-semantic-map.v1` evidence and proposes formula extensions without changing the source workbook.

The planner is intentionally conservative. It only extends a forecast row when the target sheet is deterministically identified as an income-statement or budget/forecast sheet, the time axis is monthly with explicitly marked forecast periods, the target cell is blank, and the immediately preceding period contains a workbook formula or a formula cell already proposed earlier in the same dry run.

Every proposed operation resolves to FMR's governed `fmr.formula.forecast_column_copy.v1` specification. The output contains exact target cells, source cells, formula-spec identifiers, dependency bindings and validation checks. It never contains raw formula text or financial cell values.

A row that cannot satisfy these conditions is recorded in `unresolved`. Any unresolved formula target causes `ready_for_write=false`. This is the expected fail-closed result for a workbook that needs human mapping or a later driver-based planning capability.

This work package does **not** execute the plan. Existing Native XLSX realization, write-plan and executor contracts remain separate and unchanged.
