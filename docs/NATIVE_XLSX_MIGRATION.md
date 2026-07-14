# Native XLSX migration

## Status

WP-NX-10 moved the workbook implementation and its authoritative contracts into
the Native XLSX provider. This changes ownership, not behavior. Existing Python,
CLI, HTTP and packaged-contract interfaces remain supported.

## Python imports

New provider-specific code uses:

```python
from fmr.providers.native_xlsx.workbook import inspect_workbook_bytes
```

The historical import remains an object-identical compatibility alias:

```python
from fmr.workbook import inspect_workbook_bytes
```

Every `fmr.workbook` module is a thin façade. It contains no inspection,
planning, formula, execution, population or calculation implementation.

## Contracts

Authoritative Native XLSX contracts are packaged in:

```text
fmr.providers.native_xlsx.contracts
```

Workbook-prefixed schemas remain available from `fmr.contracts` for consumers
that resolve the historical resource path. CI requires every compatibility copy
to be byte-identical to its provider-owned source.

## CLI and HTTP compatibility

Workbook-specific commands and v1 HTTP routes continue to work during the 1.x
line. Provider-neutral integrations should use `route-job`, `prepare-handoff`,
`execute-job`, `validate-job-result` and their `/api/v2` equivalents.

## Deprecation and removal policy

- No compatibility import, command, route or contract path is removed in 1.x.
- New functionality is added only to provider-neutral interfaces or the Native
  XLSX provider namespace.
- A removal proposal requires demonstrated provider-neutral parity, a published
  inventory of affected interfaces and a major-version change.
- Runtime warnings are intentionally deferred until a removal version exists;
  importing a supported compatibility interface must not produce noisy warnings.

This policy preserves existing integrations without allowing the compatibility
namespace to regain ownership of workbook behavior.
