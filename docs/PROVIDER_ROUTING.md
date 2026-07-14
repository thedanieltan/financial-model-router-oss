# Provider routing

## Lifecycle

1. Parse and validate `model-job.v2`.
2. Classify an explicit or inferred provider-neutral model family.
3. Discover versioned provider and package manifests without importing provider execution code.
4. Reject packages that violate job or policy constraints.
5. Report data, assumption, adapter, runtime and validation readiness for every surviving package.
6. Rank executable packages deterministically and emit `route-decision.v2`.
7. Compile a hash-pinned `provider-handoff.v1`; unresolved requirements keep it blocked.
8. Execute only the selected provider. No fallback occurs after execution starts.
9. Emit a value-free `execution-result.v1` chained to the job, route, handoff, provider, package and outputs.

## Built-in providers

`native-xlsx@1.0.0` is local, open-source and network-free. Its generic budget
package accepts `canonical-financial-data.v2`, produces an XLSX workbook
atomically and validates workbook structure and formulas. The broader proven
workbook runtime remains accessible through the Native XLSX compatibility module.

`reference-handoff@1.0.0` creates a deterministic handoff receipt and deliberately
does not execute a financial model. It proves that FMR routes implementations,
not just Excel generation.

## Policy and no-route behaviour

The default policy prefers the reference provider when both packages are ready.
The local-only policy rejects it and selects Native XLSX. Provider preference is
only a ranking input; it never overrides privacy, network, licensing, format,
industry, version or runtime constraints. If no package is ready, FMR returns
`no_route` with candidate readiness and rejection reasons.

## Security and privacy

Jobs and handoffs contain references and hashes, not secrets. Embedded secret,
password, token and API-key fields are rejected during handoff compilation.
Execution receipts contain hashes, counts, statuses and artifact references, not
input financial values. HTTP execution writes only beneath FMR's temporary output
directory. Provider code is imported only after a ready handoff is accepted.
Native execution runs in a bounded provider process which is terminated and its
partial output removed on timeout. FMR performs no automatic retries; receipts
state whether a caller may retry.

## Acceptance boundary

The synthetic Native XLSX proof validates local package execution and the output
workbook. It does not claim that LibreOffice is installed. Spreadsheet-engine
recalculation continues to use the existing optional acceptance path and is
reported separately from implementation and routing conformance.
