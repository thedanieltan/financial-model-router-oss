# Existing-code inventory

This inventory records the current disposition at the WP1 boundary. “Current”
describes where code lives today; “target” describes ownership after migration.
The migration is deliberately staged so existing interfaces remain operational.

| Current modules | Classification | Target disposition |
|---|---|---|
| `router.py`, `readiness.py` | Router core | Move behind `fmr.core`; replace v1 contracts in WP2/WP4 |
| `model_specs.py`, routing types in `types.py` | Compatibility layer with mixed concerns | Split provider-neutral families into `fmr.core` and XLSX operations into Native XLSX |
| `plan.py` | Compatibility layer | Retain legacy transformation plan; provider handoffs supersede it |
| `financial_data/package.py` | Source adapter | Move statement CSV ingestion to `fmr.adapters.sources` |
| `financial_data/common.py`, canonical portions of `types.py` | Canonical financial-data layer | Move to `fmr.data` |
| `financial_data/mapping.py` | Canonical financial-data layer | Retain deterministic concept mapping in `fmr.data` |
| `financial_data/binding.py` | Mixed compatibility layer | Split canonical readiness from Native XLSX slot binding |
| `workbook/**` | Native XLSX compatibility implementation | Owned and exported through `fmr.providers.native_xlsx`; paths remain for backward compatibility |
| workbook-prefixed schemas in `contracts/` | Native XLSX provider contracts | Relocate ownership without breaking packaged schema paths during migration |
| financial-data schemas in `contracts/` | Canonical data/source-adapter contracts | Evolve under provider-neutral contracts |
| `model-request.v1`, `model-recommendation.v1`, `transformation-plan.v1` | Compatibility contracts | Superseded, not silently changed, by v2 job/decision contracts |
| `dispatch.py`, `input_dispatch.py` | Native XLSX compatibility interface | Keep legacy CLI wrappers until provider-neutral commands reach parity |
| `financial_data_dispatch.py` | Source/canonical compatibility interface | Keep command compatibility while adapters move |
| `cli.py`, `entrypoint.py`, `__main__.py` | Compatibility interface | Dispatch to provider-neutral lifecycle plus deprecated legacy commands |
| `api/**` | Compatibility interface | Preserve HTTP routes; add provider-neutral routes without embedding policy |
| `web/**` | Compatibility interface | Evolve into a workbench showing candidates and rejection reasons |
| `fixtures/**` | Router-core compatibility fixtures | Replace with v2 jobs and provider conformance fixtures |

## Duplicated or obsolete candidates

No module is deleted in WP1. `cli.py` versus the composed dispatchers, v1 model
contracts, and workbook operations embedded in `model_specs.py` are confirmed
migration candidates. They become obsolete only after parity tests prove the new
interfaces. Until then they are compatibility code, not router architecture.

## Freeze rule

The new `fmr.core` namespace may not import spreadsheet libraries, LibreOffice
adapters, `fmr.workbook`, or `fmr.providers.native_xlsx`. Provider discovery must
read manifests without importing provider execution code. The repository boundary
tests enforce this rule while the implementation is migrated.
