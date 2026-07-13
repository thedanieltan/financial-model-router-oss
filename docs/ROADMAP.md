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

## 0.3 — workbook patch contracts

- compile `workbook-analysis.v1` into `workbook-patch.v1`;
- pin source, analysis and transformation-plan hashes;
- map approved high-level operations into additive patch intents;
- define preconditions, rollback order and output checks;
- validate `workbook-patch-receipt.v1` execution and rollback records;
- do not execute patch operations.

## 0.4 — workbook executor

- copy the source workbook;
- resolve exact targets against the approved operation specifications;
- apply additive patch operations;
- emit operation receipts;
- verify formulas and links;
- support rollback;
- reopen and validate the output.

## Later

Additional model families will be added only with deterministic specifications and acceptance tests.
