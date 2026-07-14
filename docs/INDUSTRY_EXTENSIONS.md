# Industry extensions

FMR's router remains industry-agnostic. Industry knowledge is added through
versioned vocabulary documents and provider-owned model packages, not by adding
industry formulas or workbook layouts to `fmr.core`.

The built-in vocabulary registry contains:

- core financials;
- SaaS;
- real estate;
- logistics;
- hospitality;
- energy;
- banking; and
- insurance.

Aliases are normalized by exact declarative matches. For example, `software as a
service` maps to `saas` and `property development` maps to `real_estate`. Unknown
terms remain explicit normalized identifiers; fuzzy or generative classification
is not used.

Vocabulary presence does not claim executable model support. A provider may
advertise an industry only when a package manifest and end-to-end fixture prove
the required data, assumptions, deliverables, output artifacts and checks.

The first specialist implementation is
`python-forecast/saas-budget-forecast`. It consumes explicit MRR and customer
history plus growth, churn, gross-margin and scenario assumptions. It produces
forecast MRR, ARR, customers, additions, churn, average revenue per customer and
gross profit. Generic packages remain available but cannot satisfy the
`saas_unit_economics` deliverable.
