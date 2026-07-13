# Roadmap

## 0.1 — routing and planning

- deterministic model selection;
- readiness and gap analysis;
- machine-readable transformation plans;
- synthetic fixtures and contract schemas;
- local developer API and browser workbench.

## 0.2 — workbook inspection

- deterministic `.xlsx` archive inspection;
- sheet, period and metric classification;
- formula and hardcoded-value counts;
- hidden-sheet, defined-name and external-link reporting;
- `workbook-map.v1` contract;
- CLI, Python, HTTP and browser interfaces.

## 0.2.1 — workbook evidence and analysis

- derive conservative model inputs from `workbook-map.v1`;
- retain evidence and confidence for every derived item;
- merge workbook evidence with an explicit model request;
- return `workbook-analysis.v1` with recommendation and transformation plan;
- never infer assumptions or mutate the workbook.

## 0.3 — governed workbook planning

Delivered contracts:

- `workbook-patch.v1` and rollback-receipt requirements;
- versioned operation specifications and semantic target resolution;
- collision-checked coordinate planning;
- FMR-owned content specifications;
- restricted formula and style realization; and
- explicit dry-run write planning.

Planning remains deterministic and does not open a workbook for writing.

## 0.4 — transactional workbook executor

- install execution separately through the `executor` package extra;
- verify the source workbook SHA-256 and size;
- reject blocked write plans, external links and unsupported workbook features;
- apply only accepted sheet, value, input, formula and style records;
- refuse source overwrite and existing output paths;
- write to a temporary file and publish the output atomically;
- reopen and verify every accepted record;
- request full recalculation when Excel next opens the output;
- return `workbook-execution-receipt.v1` with state hashes rather than cell values;
- expose Python, CLI, local HTTP and browser interfaces; and
- generate all acceptance workbooks at test runtime.

## 0.4.1 — calculated-output acceptance

- discover an optional LibreOffice or `soffice` calculation engine;
- run the engine headlessly with an isolated temporary profile and bounded timeout;
- accept workbooks recalculated by an external spreadsheet engine;
- verify populated input ranges and immutable write records before calculation;
- verify immutable records and populated inputs remain intact after calculation;
- reopen the calculated workbook in formula and data-only modes;
- reject missing cached results, spreadsheet errors, output-type mismatches and sign violations;
- scan every workbook formula, not only FMR-generated formulas;
- emit `workbook-calculation-acceptance.v1` without input or calculated values;
- publish calculated workbook bytes only when acceptance passes;
- expose Python, CLI, local HTTP and browser interfaces; and
- separate engine-independent contract tests from live LibreOffice acceptance.

## Later

Additional model families and calculation-engine adapters will be added only with deterministic specifications and acceptance tests.
