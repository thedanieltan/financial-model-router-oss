# FMR OSS Practitioner Roadmap

## Decision

`financial-model-router-oss` is the canonical repo going forward.

The private `financial-model-router` repo is frozen and should only be used as a salvage source for useful ideas, formulas, tests and UI snippets.

## Product target

FMR OSS should become an open-source financial modelling router and workbook generator for practitioner workflows.

The product must be usable by finance practitioners without asking them to understand provider manifests, JSON handoffs, model-spec contracts or internal routing architecture.

## Non-goals

- Do not build another abstract provider-router demo before proving a practitioner workflow.
- Do not require API keys for the first usable workflow.
- Do not require practitioners to write JSON.
- Do not provide accounting, tax, investment, valuation or lending advice.
- Do not migrate the full private repository.

## Slice 1: SaaS Budget and Forecast Workbook

This is the first practitioner-usable workflow.

### User story

A finance manager or FP&A practitioner needs to build a 12-month SaaS budget or forecast.

They should be able to open the local app, enter assumptions in forms, generate a workbook, review checks and export the file.

### Required workflow

1. Open local app.
2. Choose SaaS Budget and Forecast.
3. Enter assumptions in plain forms.
4. Generate workbook.
5. Review checks and summary.
6. Export XLSX.

### Required sheets

- Summary
- Assumptions
- ARR Bridge
- Revenue Forecast
- Opex and Headcount
- Cash Runway
- Scenarios
- Checks

### Required calculations

- opening ARR
- new ARR
- expansion ARR
- contraction ARR
- churned ARR
- ending ARR
- gross retention
- net revenue retention
- ARR growth
- gross profit
- sales efficiency
- EBITDA proxy
- free cash flow proxy
- cash runway

### Required checks

- ARR bridge ties
- gross margin is between 0% and 100%
- retention metrics are in reviewable ranges
- runway is computed from cash and burn assumptions
- scenario output changes when assumptions change

## Acceptance criteria

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
fmr serve
```

Manual practitioner path:

1. Open the browser workbench.
2. Complete the SaaS Budget and Forecast form.
3. Generate a workbook.
4. Open the workbook in Excel or LibreOffice.
5. Confirm formulas, checks and summary are visible.
6. Export/share the workbook.

## Promotion from private FMR

Only selectively salvage:

- model-family taxonomy
- simple executor formulas
- QA check language
- relevant tests
- UI patterns that reduce friction

Do not copy the private repo wholesale.

## Next slices after Slice 1

1. REIT NAV and AFFO workbook.
2. Operating-company 3-statement and DCF workbook.
3. Debt capacity and refinancing workbook.
4. Project finance DSCR and LLCR workbook.

## Release gates

A slice is not accepted until:

- tests pass from a clean checkout
- UI path works without JSON
- generated workbook opens successfully
- output has practitioner-readable sheets
- README documents the practitioner path
- GitHub Pages landing page links to the current test workflow
