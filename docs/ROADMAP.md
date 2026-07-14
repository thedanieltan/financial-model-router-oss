# Roadmap

The authoritative product boundary is [PRODUCT_CHARTER.md](PRODUCT_CHARTER.md).
Implementation, deployment and live acceptance are tracked separately; passing
contract tests does not claim that an optional provider runtime is installed.

| Phase | Outcome | Status |
|---|---|---|
| Existing workbook runtime | XLSX planning, writing, population and validation | Built as legacy implementation |
| Existing data intake | Statement CSV normalization and semantic mapping | Built |
| 0.6 Product realignment | Charter, code inventory, target namespaces and core freeze | In progress |
| 0.7 Job and family contracts | Provider-neutral `model-job.v2` and family definitions | Pending |
| 0.8 Provider architecture | Manifests, registry, Native XLSX and handoff-only providers | Pending |
| 0.9 Routing engine v2 | Constraint filtering, readiness, policy ranking and no-route results | Pending |
| 1.0-alpha Data and handoff | Canonical data, source/provider adapters and pinned handoffs | Pending |
| 1.0-beta Native XLSX extraction | Existing workbook runtime behind provider interface | Pending |
| 1.0-rc Execution lifecycle | Idempotent local and handoff-only orchestration | Pending |
| 1.0 Router proof | Two providers, competing route, no-route and policy-dependent route | Pending |
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
