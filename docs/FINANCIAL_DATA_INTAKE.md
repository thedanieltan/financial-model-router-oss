# Provider-neutral financial-data intake

FMR 0.5 normalizes statement exports, maps source rows to a small canonical concept registry and binds those concepts or explicit constants to semantic workbook input slots.

The core does not depend on an accounting vendor or integration service.

## Statement CSV

The first adapter accepts UTF-8 CSV with exactly these columns:

```text
entity_id,entity_name,currency,period_end,period_type,statement_type,balance_type,account_code,account_name,amount,source_ref
```

Rules:

- one entity and currency per file;
- currency is a three-letter uppercase code;
- `period_end` uses `YYYY-MM-DD`;
- `period_type` is `actual`, `budget` or `forecast`;
- `statement_type` is `income_statement`, `balance_sheet`, `cash_flow` or `operating_metric`;
- `balance_type` is `flow` or `point_in_time`;
- income-statement and cash-flow rows are flows;
- balance-sheet rows are point-in-time values;
- amounts must be finite decimals; and
- duplicate account-period rows are rejected.

The normalized `financial-data-package.v1` stores amounts as canonical decimal strings. This avoids changing source precision during normalization.

## Account mapping

`financial-concept-registry.v1` defines the initial FMR concepts and exact aliases. The registry currently covers revenue, operating costs, cash, debt, receivables, inventory, payables, capital expenditure, depreciation, interest, tax, EBITDA, operating profit, net income and operating cash flow.

The mapper applies, in order:

1. an explicit account-code rule;
2. an explicit exact account-name rule; or
3. a built-in exact alias.

There is no fuzzy matching. Unmapped rows remain visible. Conflicting exact rules and statement-shape mismatches are blockers.

A `financial-data-mapping-profile.v1` uses rules shaped as:

```json
{
  "account_code": "6000",
  "account_name": null,
  "concept_id": "operating_costs"
}
```

`financial-data-mapping-result.v1` preserves every source row, its status, candidates, method and evidence. Mapped rows are aggregated by concept and period with source row IDs retained.

## Workbook binding

A `financial-data-binding-profile.v1` maps semantic workbook slot IDs—not FMR write-record IDs—to either a concept or an explicit constant.

Concept binding:

```json
{
  "slot_id": "volume_driver",
  "source_type": "concept",
  "concept_id": "revenue",
  "selector": "period_series"
}
```

Constant binding:

```json
{
  "slot_id": "growth_rate",
  "source_type": "constant",
  "value_type": "number",
  "value": 0.05
}
```

Selectors:

- `period_series`: use values in package period order; the count must equal the reserved range;
- `latest`: use the latest available value; the target must contain one cell; and
- `repeat_latest`: repeat the latest value across the reserved range.

The first release accepts numeric and boolean workbook values. Text assumptions remain explicit and unresolved rather than being inferred.

`workbook-input-binding-plan.v1` lists bound and unresolved records. `workbook-input-set.v1` is emitted only when:

- the mapping result has no blockers;
- every reserved input record has one semantic binding;
- every selected concept exists;
- the selected value count matches the reserved range; and
- the write plan and execution receipt hashes match.

## CLI

```bash
fmr financial-concepts --output concepts.json

fmr import-statement-csv statements.csv \
  --output financial-data-package.json

fmr make-financial-mapping-profile mapping-rules.json \
  --output mapping-profile.json

fmr map-financial-data financial-data-package.json \
  --profile mapping-profile.json \
  --output mapping-result.json

fmr make-financial-binding-profile slot-bindings.json \
  --output binding-profile.json

fmr plan-financial-bindings \
  financial-data-package.json mapping-result.json binding-profile.json \
  write-plan.json execution-receipt.json \
  --output input-binding-plan.json

fmr compile-financial-input-set \
  input-binding-plan.json write-plan.json execution-receipt.json \
  --output input-set.json
```

The resulting input set can be passed to the existing governed population command.

## HTTP API

```text
GET  /api/v1/financial-concepts
POST /api/v1/financial-data/packages/from-csv
POST /api/v1/financial-data/mapping-profiles
POST /api/v1/financial-data/mappings
POST /api/v1/financial-data/binding-profiles
POST /api/v1/financial-data/binding-plans
POST /api/v1/financial-data/input-sets
```

Validation endpoints are available for packages, mapping results and binding plans.

## Boundary

FMR does not guess unknown accounts, fabricate missing periods, convert currencies, consolidate entities or determine operational drivers from financial statements. Those capabilities require separate deterministic contracts and tests.

Input packages, binding plans and input sets are value-bearing working artifacts. Population and calculation receipts remain value-free.
