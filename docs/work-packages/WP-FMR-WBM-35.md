# WP-FMR-WBM-35 — Read-only workbook semantic map

## Outcome

Upgrade FMR's existing Native XLSX inspection pipeline so an agent can understand where financial statements, schedules, periods, metrics and direct formula dependencies live before any workbook mutation is permitted.

## Included

- `workbook-semantic-map.v1` provider-owned contract plus byte-identical compatibility copy;
- annual, monthly and quarterly period recognition;
- explicit actual/budget/forecast classification where workbook text supports it;
- broader financial sheet-role classification for budget/forecast, headcount, revenue, capex, working capital and management-summary tabs;
- deterministic financial metric aliases;
- cell-level metric and period coordinates without financial numeric values;
- explicit currency and scale evidence;
- formula hashes, direct A1/range references and cross-sheet dependency edges;
- read-only `fmr semantic-map` CLI;
- synthetic acceptance fixtures covering differently structured finance workbooks.

## Excluded

- workbook writes;
- LLM-based semantic guessing;
- calculation of financial values;
- formula generation;
- approval of ambiguous mappings;
- chart/pivot semantic interpretation;
- practitioner/live acceptance.

## Implementation acceptance gates

Implementation passes only when:

1. mapping leaves source XLSX bytes unchanged;
2. the same workbook bytes produce the same semantic map;
3. provider and compatibility contracts are byte-identical;
4. emitted maps validate against JSON Schema;
5. monthly, quarterly and annual period fixtures map deterministically;
6. income statement, budget/forecast, headcount and revenue-driver fixtures map correctly;
7. direct local and cross-sheet formula dependencies are recorded without publishing raw formulas;
8. financial numeric cell values are not included in the semantic map;
9. unknown labels fail to `unknown` rather than being guessed; and
10. the repository test suite remains green.

## Next gate

WP-FMR-FML-36 should consume an accepted semantic map and produce a **dry-run formula/model plan** for one monthly FP&A request. It must show every proposed sheet, cell, formula specification, source coordinate and validation check before changing a workbook.
