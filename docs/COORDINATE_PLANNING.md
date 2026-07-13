# Coordinate planning

Coordinate planning converts an accepted semantic target resolution into deterministic sheet positions and A1 ranges. It does not modify the workbook.

## Inputs

The planner requires:

- `workbook-analysis.v1`;
- `workbook-patch.v1`;
- `workbook-target-resolution.v1`; and
- an explicit `forecast_period_count` between 1 and 60.

The source contracts are validated and deterministically recomputed before coordinates are accepted.

## Coordinate rules

`workbook-coordinate-rule-registry.v1` contains one rule for every approved workbook operation. A rule defines:

- allocation kind;
- fixed rows and columns, where applicable;
- the variable dimension parameter, where applicable;
- the gap before an appended block; and
- whether an existing target already satisfies the operation.

The registry is hashed and pinned by every coordinate plan.

## Allocation kinds

### `sheet_block`

Reserves the initial block on a new sheet. A unique existing sheet may satisfy the operation without reserving another range.

### `append_block`

Places a fixed-size block below the source used range and all earlier planned ranges on that sheet.

### `column_extension`

Places an explicit number of columns to the right of the occupied range. The planner does not assume a forecast horizon.

### `reference_only`

Records that an operation uses resolved workbook components but requires no new coordinate allocation.

## Collision model

The planner treats these ranges as occupied:

1. each source sheet's complete used-range bounding rectangle; and
2. every range allocated earlier in operation order.

A candidate allocation is rejected if it overlaps any occupied rectangle. The planner does not infer that gaps inside a source used range are safe.

## Excel limits

Every range is checked against:

- maximum row: `1,048,576`;
- maximum column: `16,384` (`XFD`); and
- maximum worksheet-name length and invalid worksheet-name characters for planned sheets.

Overflow produces a blocker rather than a truncated range.

## Output

`workbook-coordinate-plan.v1` contains:

- source, patch and target-resolution identifiers;
- target-resolution and coordinate-registry hashes;
- explicit layout parameters;
- one coordinate plan per operation;
- allocated A1 ranges with numeric boundaries;
- source occupancy seen before each allocation;
- planned sheet positions;
- blockers; and
- control flags.

`ready_for_executor` means the coordinate document is complete and collision-free. `execution_supported_by_this_release` remains `false`.

## Excluded

Coordinate plans contain no:

- values;
- formulas;
- cell writes;
- formatting instructions;
- macros or scripts;
- workbook bytes; or
- execution results.

Those concerns require separate specifications and acceptance gates.
