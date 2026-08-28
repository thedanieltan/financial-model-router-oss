# WP-FMR-MTH-33 — Reference-grounded analyst methodology

## Outcome

Add a machine-readable, provider-neutral description of the repeatable analyst
workflow behind every model family currently registered in FMR.

This work package changes knowledge and governance. It does not change model
formulas, provider execution, routing policy or financial outputs.

## Why

Existing family playbooks answer whether a model family is suitable, what it
requires and what it returns. They do not define the ordered manual process an
analyst follows between scope and commentary-ready output.

FMR should automate that existing process rather than invent a new modelling
methodology.

## Included

- `analyst-workflow-method.v1` JSON Schema;
- one reference-grounded method for budget/forecast, integrated three-statement,
  operating-company DCF and debt-capacity/refinancing;
- step-level execution classes separating source facts, deterministic work,
  governed rules and judgment;
- requirement classes for universal, common, conditional and variant steps;
- step-level source provenance;
- expanded public teaching/reference corpus with explicit reuse status;
- commentary-ready evidence as the end of the deterministic workflow boundary;
- knowledge-registry loading, deterministic hashing and lookup of methods;
- package-data inclusion for clean-wheel installs;
- structural and fail-closed tests.

## Governance

- reference-only sources remain `reference_only`;
- no third-party workbook, template, formula, screenshot or course text is
  distributed;
- provider-specific fields remain forbidden from methodology contracts;
- `reference_grounded` does not imply practitioner acceptance;
- `practitioner_accepted` remains an external-evidence state;
- implementation, deployment and production acceptance remain separate.

## Acceptance gates

Implementation may be marked passed only when:

1. every registered model family has exactly one method;
2. every method validates against its JSON Schema;
3. step sequences are contiguous and ordered;
4. all method and step source references resolve;
5. every method contains scope, validation, outputs and commentary-evidence
   stages;
6. provider-specific or undeclared fields fail closed;
7. reference-only sources cannot be promoted implicitly;
8. a clean installed wheel contains the method corpus; and
9. the repository test suite remains green.

Deployment and practitioner/live acceptance are out of scope for this package.

## Next work package

`WP-FMR-WFL-34` should map the budget/forecast analyst method onto one existing
monthly FP&A workflow end to end:

actuals → reconciliation → variance/driver analysis → forecast roll-forward →
scenario comparison → checked management outputs → commentary evidence.

That package should reuse existing FMR model/provider code wherever it conforms
to the method and expose explicit blockers where it does not.
