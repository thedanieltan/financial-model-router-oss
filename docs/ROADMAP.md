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

## 0.3.1 — operation specifications and target resolution

- publish one versioned specification for every approved operation;
- resolve semantic roles to existing, new, planned or set targets;
- block ambiguous targets and missing required statement roles;
- pin the operation registry and patch hashes;
- return `workbook-target-resolution.v1`;
- do not assign write coordinates or modify the workbook.

## 0.3.2 — coordinate planning

- publish one versioned coordinate rule for every approved operation;
- require an explicit forecast-period count for variable-width extensions;
- reserve new-sheet, appended-section and right-extension ranges;
- treat source used ranges and prior allocations as occupied;
- block collisions and Excel row or column overflow;
- return `workbook-coordinate-plan.v1`;
- do not emit values, formulas or workbook writes.

## 0.3.3 — content planning

- publish one versioned content specification for every approved operation;
- assign FMR-owned labels and input placeholders to reserved ranges;
- assign symbolic formula, period, reference and validation identifiers;
- assign semantic format roles without colours, fonts or number formats;
- keep every slot inside its coordinate allocation;
- return `workbook-content-plan.v1`;
- do not emit values, formula expressions or workbook writes.

## 0.3.4 — formula and style specifications

- define formula identifiers as deterministic expression templates;
- define dependency, sign and dimensionality rules;
- define number-format and style roles separately from model logic;
- validate formulas and styles without editing a workbook.

## 0.4 — workbook executor

- copy the source workbook;
- apply only accepted coordinate, content, formula and style plans;
- emit operation receipts;
- verify formulas and links against accepted specifications;
- support rollback;
- reopen and validate the output.

## Later

Additional model families will be added only with deterministic specifications and acceptance tests.
