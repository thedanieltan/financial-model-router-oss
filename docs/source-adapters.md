# Source adapters

FMR imports tabular exports through `source-adapter-profile.v1`. A profile pins the source system, export type, file format, sheet, version, and an exact mapping from canonical fields to external headers. Discovery never guesses headers, values, concepts, or assumptions.

Supported export shapes are trial balance, financial statement, general ledger, budget-versus-actual, debt schedule, and operational drivers. CSV and XLSX are supported; XLSX formula cells in mapped fields are rejected because ingestion does not execute workbooks.

```console
fmr import-tabular-source profile.json export.xlsx \
  --entity-id acme --currency SGD --output canonical.json
```

Multiple compatible packages can be combined without inference:

```console
fmr merge-canonical-data statements.json drivers.json --output model-input.json
```

## Vendor exports

`source_system` can identify `xero`, `quickbooks`, or `erpnext`, but FMR intentionally ships no guessed universal vendor-column preset. Export layouts can vary by report, product version, configuration, and locale. Operators must validate a versioned mapping profile against the actual export they accept.

The implementation boundary is file-export ingestion, not a live vendor API integration. Official vendor documentation confirms these export paths:

- [Xero data and report exports](https://central.xero.com/s/article/Export-data-out-of-Xero-US)
- [Xero general-ledger exports](https://central.xero.com/s/article/Export-general-ledger-data-out-of-Xero)
- [QuickBooks Online report exports](https://quickbooks.intuit.com/learn-support/en-us/help-article/list-management/export-reports-lists-data-quickbooks-online/L1xleDrLp_US_en_US)
- [QuickBooks Desktop CSV and Excel exports](https://quickbooks.intuit.com/learn-support/en-us/help-article/manage-lists/import-export-csv-files/L9AiGRdT9_US_en_US)
- [ERPNext data exports](https://docs.frappe.io/erpnext/data-export)

Every canonical result records the source file name, SHA-256 digest, source system, profile ID, and profile version. Missing headers, incomplete series, duplicate observations, non-finite numbers, unbalanced trial balances, and broken debt roll-forwards fail closed.
