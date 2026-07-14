# Roadmap

The authoritative product boundary is [PRODUCT_CHARTER.md](PRODUCT_CHARTER.md).
Implementation, deployment and live acceptance are tracked separately; passing
contract tests does not claim that an optional provider runtime is installed.

| Phase | Outcome | Status |
|---|---|---|
| Existing workbook runtime | XLSX planning, writing, population and validation | Built as legacy implementation |
| Existing data intake | Statement CSV normalization and semantic mapping | Built |
| 0.6 Product realignment | Charter, code inventory, target namespaces and core freeze | Built |
| 0.7 Job and family contracts | Provider-neutral `model-job.v2` and family definitions | Built; strict schemas and fixtures added in WP-RTR-09 |
| 0.8 Provider architecture | Manifest-only discovery plus late-loaded adapter and executor entry points | Built for local plugins |
| 0.9 Routing engine v2 | Constraint filtering, readiness, policy ranking and no-route results | Built for registered providers |
| 1.0-alpha Data and handoff | Canonical data and a strictly verified job-route-handoff hash chain | Built |
| Native XLSX ownership boundary | Router core is spreadsheet-independent; legacy interfaces remain compatible | Built |
| Physical Native XLSX extraction | Provider owns workbook implementation and schemas; `fmr.workbook` is façade-only | Built in WP-NX-10 |
| Legacy workbook interface deprecation | Migration policy published; compatibility retained through the 1.x line | Built in WP-NX-10; removal deferred |
| Execution lifecycle | Typed requests, enforced controls, SQLite idempotency and artifact validation | Local implementation built |
| Interchangeable model proof | Native XLSX and Python Forecast execute the same budget family under policy | Built with synthetic acceptance |
| FMR `1.0.0-alpha` | Provider-router integrity and local execution preview | Current maturity |
| Production FMR 1.0 | Remote execution security and deployment-specific operational acceptance | Not accepted |
| 1.1–1.6 Ecosystem | SDK, registry, industries, sources, organization policies and agents | Pending |
| 2.0 Distributed routing | Signed remote discovery and secure distributed execution | Deferred until local stability |

## Immediate work packages

1. **Product boundary** — publish the charter, classify existing code, scaffold
   target ownership, freeze workbook-specific work in core and preserve interfaces.
2. **Job and family contracts** — add `model-job.v2`, provider-neutral model-family
   definitions, explicit ambiguity and structured unsupported-family results.
3. **Provider manifests** — validate versioned provider/package manifests and
   register Native XLSX plus a non-executing reference handoff provider.
4. **Routing engine v2** — discover candidates, enforce hard constraints, evaluate
   readiness, rank deterministically and return a complete route decision.
5. **Provider handoff** — select adapters, compile a hash-pinned handoff and block
   it while mandatory requirements remain unresolved.
6. **Native XLSX migration** — move the workbook runtime behind the provider
   interface, retain compatibility wrappers and remove spreadsheet dependencies
   from core.
7. **Execution orchestration** — standardize states, idempotency, timeouts, atomic
   outputs, validation and value-free receipts for local and handoff-only modes.
8. **FMR 1.0 proof** — publish conformance tests and prove Native XLSX,
   alternative-provider, no-route and policy-dependent routing across Python, CLI,
   HTTP and the workbench.

The original eight packages established the architecture proof. WP-RTR-09 then
closed the unsafe handoff, output-contract and central-dispatch gaps. It does not
claim production FMR 1.0: remote-provider security and deployment-specific
operational acceptance remain open. Bundled
providers are acceptance-tested with synthetic canonical financial data;
LibreOffice recalculation remains optional and separately reported.

## WP-NX-10 — physical Native XLSX extraction

- workbook inspection, planning, execution, population and calculation code now
  lives under `fmr.providers.native_xlsx.workbook`;
- provider-owned workbook schemas live under
  `fmr.providers.native_xlsx.contracts`;
- `fmr.workbook` modules contain import aliases only and are covered by object-
  identity compatibility tests;
- legacy packaged contract paths remain byte-identical compatibility copies;
- production modules no longer import the legacy workbook namespace; and
- the migration and removal policy is published in
  [NATIVE_XLSX_MIGRATION.md](NATIVE_XLSX_MIGRATION.md).

## WP-RTR-09 — router integrity and release hardening

- reference handoff advertises and produces only a JSON external handoff;
- strict route, handoff, execution-result, receipt and artifact validation;
- complete canonical job → route → handoff → execution hash verification;
- provider adapters and executors loaded through installed entry points only
  after selection;
- Native XLSX performs driver-based, scenario-aware forecast-period generation;
- Python Forecast provides a second genuine budget-family implementation;
- execution mode, output policy and secret references are enforced;
- SQLite-backed cross-process idempotency revalidates cached artifacts;
- controlled JSON Schemas and valid/invalid fixtures are exercised in CI; and
- a clean-wheel provider lifecycle workflow covers discovery through execution.

## Post-1.0 sequence

- **1.1 Provider SDK:** templates, typed interfaces, fixtures, runner, conformance,
  versioning, deprecation and example providers.
- **1.2 Provider registry:** versions, lifecycle, conformance, licensing, runtime,
  privacy and availability; no arbitrary provider-count target.
- **1.3 Industry extensions:** declarative vocabularies and provider packages for
  SaaS, real estate, logistics, hospitality, energy, banking and insurance.
- **1.4 Source adapters:** trial balance, generic statements, general ledger,
  budget-versus-actual, debt, drivers, Xero, QuickBooks and ERPNext by demand.
- **1.5 Organization routing:** private registries, company templates, allowlists,
  precedence, approved versions, environment rules and retention policies.
- **1.6 Agent access:** route simulation, discovery, handoff, execution, validation
  and receipts through HTTP, CLI and an optional MCP server.
- **2.0 Distributed routing:** remote discovery, signed manifests, workers, health,
  regions, cost, quotas, comparisons and multi-step pipelines.
