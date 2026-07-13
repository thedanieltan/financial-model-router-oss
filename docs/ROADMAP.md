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

## 0.4.2 — governed input population

- compile explicit UTF-8 CSV rows into `workbook-input-set.v1`;
- allow only finite numeric and boolean values;
- require complete, ordered coverage of every `reserve_input` record and cell;
- pin the write plan, execution receipt and declared source provenance;
- verify the selected workbook hash and size against the execution output;
- prove generated workbook records remain immutable and input ranges remain blank;
- populate only reserved input ranges;
- reopen and verify exact populated inputs and every immutable record;
- atomically publish a separate populated workbook;
- emit `workbook-input-population-receipt.v1` without input values;
- validate the hash chain from population output into calculation acceptance;
- expose Python, CLI, local HTTP and browser interfaces; and
- keep all acceptance workbooks synthetic and runtime-generated.

## 0.5 — provider-neutral financial-data intake

- normalize one-entity statement CSVs into `financial-data-package.v1`;
- preserve source precision as decimal strings and retain row provenance;
- publish a small versioned financial concept registry;
- apply exact built-in aliases and explicit account-code or account-name overrides;
- report unmapped, ambiguous and statement-shape-invalid rows;
- aggregate accepted account rows by concept and period;
- bind concepts or explicit constants to semantic workbook slot IDs;
- emit `workbook-input-binding-plan.v1` with bound and unresolved records;
- compile `workbook-input-set.v1` only when every reserved numeric or boolean input is covered;
- expose Python, CLI, local HTTP and browser interfaces; and
- validate the installed-wheel path from statement CSV to governed input set.

## Later

- reusable mapping-profile lifecycle and review tooling;
- provider-neutral trial-balance and XLSX adapters;
- multi-entity consolidation and currency-conversion contracts;
- deeper budget and forecast schedules;
- additional model families; and
- additional calculation-engine adapters.

Each addition requires deterministic specifications and acceptance tests.
