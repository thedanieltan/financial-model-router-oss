# Analyst methodology corpus

## Purpose

FMR is a financial-model router. It does not invent a new modelling methodology.
This corpus records independently authored, provider-neutral abstractions of the
repeatable process taught by established financial-modelling educators and
standards bodies.

The goal is to make an analyst workflow machine-readable up to a verified,
commentary-ready evidence boundary. FMR calculations remain deterministic.
Assumptions and other judgment stay explicit.

## First-principles workflow

Across model families, the reusable analyst process is:

1. define the business decision and modelling scope;
2. load governed source data and relevant history;
3. normalize and reconcile the source data;
4. set explicit assumptions and business drivers;
5. establish the model time axis and structure;
6. build supporting schedules;
7. execute the core linked calculations;
8. run mandatory validation and reconciliation checks;
9. run scenarios or sensitivities when relevant;
10. prepare decision-relevant outputs and KPIs;
11. perform variance or driver analysis when the decision requires it; and
12. prepare source-linked evidence from which stakeholder commentary can be written.

A model family may omit, repeat or specialize stages. The sequence is not a
claim that one spreadsheet layout or one formula convention is universally
correct.

## Automation boundary

Each workflow step is classified as one of four execution classes:

- `source` — obtain governed facts or source data;
- `deterministic` — calculations and reconciliations that should be reproducible;
- `governed_rule` — controlled routing, structure or evidence assembly;
- `judgment` — an explicit human or agent-assisted decision that must not be
  silently presented as sourced fact.

FMR may automate the first three classes. `judgment` inputs can be collected,
validated, versioned and attributed, but are not invented by deterministic
execution.

The workflow ends at `commentary_evidence`. Narrative commentary can be produced
by a person or an interchangeable agent only after the underlying evidence is
validated.

## Requirement classes

Steps also declare whether they are:

- `universal`;
- `common_default`;
- `conditional`; or
- `method_variant`.

This prevents FMR from forcing one implementation on model families where
legitimate professional approaches differ.

## Initial source corpus

| Source | Role in corpus | Reuse status |
| --- | --- | --- |
| FAST Standard | Cross-family structure, transparency, simplicity, scenarios | CC BY 4.0 |
| ICAEW Financial Modelling Code | Robustness, transparency and review principles | Reference only |
| Gridlines Essential Financial Modelling | Three-statement construction and supporting schedules | Reference only |
| Gridlines three-statement explainer | Statement linking under assumptions | Reference only |
| CFI FP&A Excel Modeling | FP&A model construction, aggregation, variance and reporting sequence | Reference only |
| CFI Driver-Based Forecasting | Driver identification/validation and scenarios | Reference only |
| CFI FP&A Variance Pt.1 / Pt.2 | Monthly review, roll-forward and variance workflow | Reference only |
| CFI Debt and Capex Analysis | Debt/capex schedules and cash-linked checks | Reference only |
| A Simple Model — Integrating Financial Statements | Historical input, statement projection and supporting schedules | Reference only |
| Macabacus Learn Finance | Operating-model, M&A and LBO construction reference for later families | Reference only |
| Aswath Damodaran valuation class | Valuation methodology and worked case structure | Reference only |
| Edward Bodmer A-Z Project Finance | Timing, operations/financing separation, debt and validation | Reference only |
| Kenji Explains three-statement walkthrough | Observable three-statement construction sequence | Reference only |

Exact URLs, retrieval dates, permitted-use status and usage notes live in
`fmr/knowledge/data/sources.json`.

## Initial family consensus

### Budget and forecast

Decision/scope → actuals and operational drivers → reconciliation → explicit
drivers/assumptions → model structure → operating schedules → aggregate forecast
→ validation → scenarios → variance/driver analysis → management outputs →
commentary evidence.

### Integrated three-statement

Decision/scope → historical statements → reconciliation → operating assumptions
→ time/link structure → supporting schedules → linked statement projection →
balance/cash/roll-forward checks → scenarios → integrated outputs → commentary
evidence.

### Operating-company DCF

Valuation scope → supported operating forecast and bridge data → normalization →
explicit discount/terminal assumptions → free-cash-flow derivation → present
value → enterprise-to-equity bridge → validation → sensitivities → valuation
outputs → commentary evidence.

### Debt capacity and refinancing

Financing scope → cash-flow/debt/term data → reconciliation → financing
assumptions → financing timeline → debt/liquidity schedules → capacity/covenant
calculations → validation → refinancing scenarios → financing outputs →
commentary evidence.

## Intellectual-property boundary

Reference-only sources are evidence that a workflow is taught or used; their
course text, videos, screenshots, formulas, templates and workbook assets are
not repository content. FMR stores independently authored abstractions of
process and control boundaries.

The existing repository IP rules continue to apply. No third-party workbook
asset is required by these methods.

## Acceptance boundary

`reference_grounded` means the workflow is traceable to declared public
references and passes FMR's structural integrity rules. It does **not** mean a
qualified practitioner has accepted the method.

Promotion to `practitioner_accepted` requires separate external evidence. Model
implementation acceptance, deployment acceptance and production acceptance also
remain separate gates.
