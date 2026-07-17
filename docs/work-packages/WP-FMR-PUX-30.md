# WP-FMR-PUX-30 — Practitioner source intake

## Problem

The workflow router removed model-family and provider-selection work from practitioners, but the first workbench still required a technical canonical reference. A finance manager or FP&A practitioner could compile a workflow but could not prepare its source without using lower-level interfaces.

## Outcome

The practitioner workbench now accepts a controlled statement CSV and explicit assumptions, converts the source into `canonical-financial-data.v2`, stores it immutably under a SHA-256 filename and injects the reference into the workflow request.

## Implemented

- downloadable statement CSV template;
- browser statement-source upload;
- UTF-8, column, entity, currency, period, statement-shape and decimal validation;
- exact built-in account aliases and explicit mapping overrides;
- incomplete mapped-series rejection;
- unmapped-row warnings without invented concepts;
- canonical statement, trial-balance, capex, working-capital, driver, assumption and provenance compilation;
- immutable managed local source storage;
- value-free `workflow-source-result.v1` metadata;
- source-aware practitioner workflow compilation;
- source-to-workflow-to-real-provider execution tests.

## Boundaries

- the source contract currently accepts the controlled statement CSV shape, not arbitrary accounting exports;
- direct Xero, ERPNext and Aether accounting packages remain source-adapter work;
- material assumptions are explicit values supplied by the practitioner;
- mapping is exact only; no fuzzy or generative account classification;
- workflow source storage is local and does not establish deployment durability;
- practitioner and production acceptance remain pending.
