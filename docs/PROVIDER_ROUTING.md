# Provider routing

## Lifecycle

1. Parse and validate `model-job.v2`.
2. Classify an explicit or inferred provider-neutral model family.
3. Discover versioned manifests without importing provider implementation code.
4. Reject packages that violate job or policy constraints.
5. Report data, assumption, adapter, executor, runtime and validation readiness.
6. Rank executable packages deterministically and emit `route-decision.v2`.
7. Compile `provider-handoff.v1` with canonical job and route snapshots.
8. Recompute the complete job, route, handoff, manifest and adapter chain before execution.
9. Load only the selected installed adapter or executor entry point. No fallback occurs after execution starts.
10. Enforce required artifact kinds, formats, hashes, validation and provider receipt before returning `completed`.

## Bundled providers

`native-xlsx@1.0.0` is local, open-source and network-free. Its generic budget
package uses explicit horizon, growth-rate and scenario assumptions to create
separate forecast periods. It emits a formula-backed XLSX workbook and a JSON
forecast and validates both artifacts.

`python-forecast@1.0.0` independently executes the same budget-and-forecast
family and emits a deterministic JSON result. `json-first` and
`spreadsheet-first` policies demonstrate genuine implementation competition.

`reference-handoff@1.1.0` produces only a JSON `external_provider_handoff`. It
does not advertise a workbook or completed financial model and cannot compete
for those deliverables.

## Plugin boundary

Manifests declare adapter and executor entry-point names. Discovery reads built-in
and configured-directory manifests without importing those entry points. After
selection and strict handoff verification, FMR resolves the declared names from
the installed `fmr.provider_adapters` and `fmr.provider_executors` Python entry-
point groups. Adding an installed provider does not require a router-core branch.

## Security and reliability

Jobs and handoffs contain references and hashes, not secrets. Embedded secret,
password, token and API-key fields are rejected. Requested execution mode must
match the provider manifest. Secret references must exactly match manifest
requirements and are resolved only through an injected resolver. HTTP supports
managed output policy only; overwrite and publication are not implemented and
are rejected rather than ignored.

Provider execution runs in a bounded child process. SQLite-backed idempotency is
shared across orchestrator processes, uses stale-claim recovery and returns a
cached result only while every output file and hash remains valid. Receipts are
value-free and contain their canonical payload and hash. FMR performs no silent
fallback or automatic retry after execution starts.

## Acceptance boundary

Synthetic Native XLSX and Python Forecast proofs validate local package
execution. The clean-wheel provider workflow covers discovery, routing, handoff,
execution, artifact validation, external handoff and no-route behavior from the
built distribution. This does not claim production remote-provider operation,
completed physical extraction of `fmr.workbook`, or installed LibreOffice.
