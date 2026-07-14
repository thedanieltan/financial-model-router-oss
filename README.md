# Financial Model Router

Financial Model Router (FMR) is an open-source, deterministic router for financial-modelling jobs. It classifies the requested model family, discovers compatible provider packages, checks constraints and readiness, selects an implementation under an explicit policy, and produces a version-pinned handoff for execution and validation.

FMR does not provide accounting, tax or investment advice. The deterministic core runs locally.

FMR `1.0.0-alpha` is a provider-router integrity preview. It includes executable **Native XLSX** and **Python Forecast** providers plus a non-modelling **reference handoff provider**. It is not accepted as production FMR 1.0. Workbook formulas, layouts and calculation engines are owned by the Native XLSX provider; the historical `fmr.workbook` namespace remains a compatibility façade. See the normative [product charter](docs/PRODUCT_CHARTER.md), [provider-routing guide](docs/PROVIDER_ROUTING.md), [Provider SDK](docs/PROVIDER_SDK.md), [code inventory](docs/CODE_INVENTORY.md), [migration guide](docs/NATIVE_XLSX_MIGRATION.md) and [roadmap](docs/ROADMAP.md).

## Provider router

The provider-neutral family registry recognizes four initial model families:

- budget and forecast;
- integrated three-statement model;
- operating-company discounted cash-flow valuation; and
- debt-capacity and refinancing analysis.

`model-job.v2` routes through explicit family classification, manifest-only provider discovery, hard constraints, readiness evaluation and deterministic policy ranking. A decision returns every candidate, rejection reason, missing requirement and fallback. Ambiguous, unsupported and no-route outcomes are first-class results.

The generic budget package is implemented by Native XLSX and Python Forecast. Both generate forecast periods from explicit growth, horizon and scenario assumptions. `json-first` and `spreadsheet-first` policies select between the genuine implementations. The reference provider advertises only a JSON external-provider handoff and never competes for an XLSX workbook or completed model.

FMR can inspect an `.xlsx` workbook and return `workbook-map.v1`. It can derive evidence-backed inputs, merge them with an explicit `model-request.v1`, and return `workbook-analysis.v1`.

A valid analysis can be compiled through versioned patch, target, coordinate, content, formula, style and write contracts. `workbook-write-plan.v1` contains explicit Excel A1 formulas and ordered sheet, value, input and style records.

FMR 0.4 applies an accepted write plan to a copied `.xlsx` workbook and emits `workbook-execution-receipt.v1` without cell values or workbook bytes.

FMR 0.4.1 recalculates a populated copy through optional LibreOffice, or accepts a workbook recalculated elsewhere. `workbook-calculation-acceptance.v1` checks immutable records, populated inputs, cached results, result types, sign conventions and spreadsheet errors without recording input or calculated values.

FMR 0.4.2 compiles explicit numeric or boolean CSV data into `workbook-input-set.v1`, populates only ranges governed by `reserve_input` records, and emits `workbook-input-population-receipt.v1` without input values.

FMR 0.5 normalizes provider-neutral statement CSVs into `financial-data-package.v1`, maps exact account labels or explicit overrides to canonical concepts, binds concepts or constants to semantic workbook slot IDs, and emits `workbook-input-set.v1` only when every reserved numeric or boolean input is covered.

Derived evidence never creates assumptions and never overrides explicit user input.

## Install

Planning and financial-data intake:

```bash
python -m pip install -e .
```

Workbook execution, input population and calculated-output validation:

```bash
python -m pip install -e ".[executor]"
```

Local recalculation additionally requires LibreOffice with the `libreoffice` or `soffice` command available. A workbook recalculated in another spreadsheet engine can be validated without invoking LibreOffice from FMR.

Developer workbench:

```bash
python -m pip install -e ".[dev-ui,executor]"
fmr serve
```

Open `http://127.0.0.1:8000` for the browser workbench or `http://127.0.0.1:8000/docs` for the API console.

The server binds to the loopback interface, stores no requests, sends no telemetry and makes no outbound network calls.

## Use the CLI

Provider-neutral lifecycle:

```bash
fmr discover-providers --output registry.json
fmr route-job model-job.json --policy default --output route-decision.json
fmr prepare-handoff model-job.json --policy local-only --output provider-handoff.json
fmr execute-job provider-handoff.json \
  --idempotency-key example-run-1 \
  --output-dir ./outputs \
  --receipt execution-result.json
fmr validate-job-result execution-result.json --handoff provider-handoff.json
```

The equivalent HTTP endpoints are under `/api/v2`; the browser workbench exposes provider candidates and rejection reasons. Python callers use `route_job`, `prepare_handoff`, `ExecutionOrchestrator` and `validate_execution_result`.

Local execution operations are available without exposing unauthenticated
administrative HTTP endpoints:

```bash
fmr operations-status --ledger .fmr-execution-ledger.sqlite3
fmr recover-executions --ledger .fmr-execution-ledger.sqlite3 --stale-after 300
fmr backup-execution-ledger --ledger .fmr-execution-ledger.sqlite3 backup.sqlite3
fmr prune-execution-artifacts --ledger .fmr-execution-ledger.sqlite3 \
  --managed-output-root ./outputs --older-than 2592000
```

Retention is a dry run unless `--apply` is supplied. See the
[operations guide](docs/OPERATIONS.md).

Provider authoring:

```bash
fmr-provider init my-provider ./my-provider
python -m pip install -e ./my-provider
fmr-provider validate ./my-provider
fmr-provider test ./my-provider
fmr-provider package ./my-provider --destination ./dist
```

Static validation never imports provider code. Executable conformance is an
explicit code-execution boundary. See the [Provider SDK guide](docs/PROVIDER_SDK.md).

Approved local provider releases can be retained in an immutable lifecycle
registry using `fmr-registry`. Submission verifies bundle and attestation hashes;
only available executable-conformant releases can become active. See the
[provider registry guide](docs/PROVIDER_REGISTRY.md).

Industry terminology is supplied through declarative vocabularies rather than
router-specific logic. The first specialist executable package is the Python
SaaS budget and unit-economics forecast. See
[industry extensions](docs/INDUSTRY_EXTENSIONS.md).

CSV and XLSX exports can be normalized through exact, versioned source-adapter
profiles. Trial balances, statements, ledgers, budget-versus-actuals, debt
schedules and operating drivers are supported without guessing vendor headers
or assumptions. See [source adapters](docs/source-adapters.md).

Financial-data intake:

```bash
fmr import-tabular-source source-profile.json export.xlsx \
  --entity-id acme --currency SGD --output canonical.json
fmr merge-canonical-data statements.json drivers.json --output model-input.json
fmr financial-concepts --output concepts.json
fmr import-statement-csv statements.csv --output financial-data-package.json
fmr make-financial-mapping-profile mapping-rules.json --output mapping-profile.json
fmr map-financial-data financial-data-package.json \
  --profile mapping-profile.json \
  --output mapping-result.json
fmr make-financial-binding-profile slot-bindings.json --output binding-profile.json
fmr plan-financial-bindings \
  financial-data-package.json mapping-result.json binding-profile.json \
  write-plan.json execution-receipt.json \
  --output input-binding-plan.json
fmr compile-financial-input-set \
  input-binding-plan.json write-plan.json execution-receipt.json \
  --output input-set.json
```

Workbook pipeline:

```bash
fmr route tests/fixtures/request-dcf-ready.json
fmr plan tests/fixtures/request-debt-blocked.json
fmr inspect model.xlsx --output workbook-map.json
fmr analyse-workbook model.xlsx request.json --output workbook-analysis.json
fmr compile-patch workbook-analysis.json --output workbook-patch.json
fmr resolve-targets workbook-analysis.json workbook-patch.json \
  --output target-resolution.json
fmr plan-coordinates workbook-analysis.json workbook-patch.json target-resolution.json \
  --forecast-period-count 5 \
  --output coordinate-plan.json
fmr plan-content coordinate-plan.json --output content-plan.json
fmr plan-realization content-plan.json --output realization-plan.json
fmr plan-writes realization-plan.json write-context.json --output write-plan.json
fmr execute-writes source.xlsx write-plan.json \
  --output executed.xlsx \
  --receipt execution-receipt.json
fmr populate-inputs executed.xlsx input-set.json write-plan.json execution-receipt.json \
  --output populated.xlsx \
  --receipt population-receipt.json
fmr calculate-output populated.xlsx write-plan.json execution-receipt.json \
  --output calculated.xlsx \
  --receipt calculation-acceptance.json
fmr validate-input-calculation-link \
  population-receipt.json calculation-acceptance.json
```

Only `.xlsx` workbooks are accepted.

Planning through `validate-write-plan` is non-mutating. Execution, input population and calculation each publish only to a new output path. Calculated workbook bytes are published only after acceptance passes.

## Design rules

- Model selection is explainable.
- Missing information is reported, not invented.
- Financial source amounts retain decimal precision during normalization.
- Account mapping uses exact aliases or explicit overrides; fuzzy matching is not used.
- Unmapped, ambiguous and statement-shape-invalid rows remain visible.
- Binding profiles use semantic slot IDs rather than write-record IDs.
- A governed input set is emitted only when every reserved input is covered.
- Assumptions are never inferred from workbook labels or financial statements.
- Existing formulas are inspected as text and never executed during inspection.
- Every plan and receipt pins its source contracts.
- Ambiguous semantic targets and dependency bindings are blocked.
- Coordinate ranges are checked against occupancy and Excel bounds.
- Formula templates use declared dependencies and forbid raw external references and circularity.
- Input slots are editable; generated output and control slots are locked.
- Execution verifies source identity and publishes atomically.
- Input-set values are never copied into population receipts.
- Calculation runs through an optional isolated spreadsheet-engine adapter.
- Formula errors and missing cached results block acceptance.
- Public fixtures and workbooks are synthetic and generated during tests.
- CLI, Python and HTTP interfaces call the same deterministic functions.

See [docs/FINANCIAL_DATA_INTAKE.md](docs/FINANCIAL_DATA_INTAKE.md), [docs/SERVICE.md](docs/SERVICE.md), [docs/WORKBOOK_INSPECTION.md](docs/WORKBOOK_INSPECTION.md), [docs/WORKBOOK_ANALYSIS.md](docs/WORKBOOK_ANALYSIS.md), [docs/WORKBOOK_PATCH.md](docs/WORKBOOK_PATCH.md), [docs/SEMANTIC_TARGET_RESOLUTION.md](docs/SEMANTIC_TARGET_RESOLUTION.md), [docs/COORDINATE_PLANNING.md](docs/COORDINATE_PLANNING.md), [docs/CONTENT_PLANNING.md](docs/CONTENT_PLANNING.md), [docs/FORMULA_STYLE_SPECIFICATIONS.md](docs/FORMULA_STYLE_SPECIFICATIONS.md), [docs/WRITE_PLANNING.md](docs/WRITE_PLANNING.md), [docs/WORKBOOK_EXECUTION.md](docs/WORKBOOK_EXECUTION.md), [docs/INPUT_POPULATION.md](docs/INPUT_POPULATION.md), [docs/CALCULATED_OUTPUT_ACCEPTANCE.md](docs/CALCULATED_OUTPUT_ACCEPTANCE.md), [docs/DEVELOPER_WORKBENCH.md](docs/DEVELOPER_WORKBENCH.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/IP_BOUNDARY.md](docs/IP_BOUNDARY.md).

## Licence

Apache License 2.0.
