# Product charter

This document is normative for Financial Model Router (FMR). Where an older
document describes FMR as a workbook generator, this charter takes precedence.

## Product purpose

FMR accepts a provider-neutral financial-modelling job, identifies the required
model family, discovers compatible model packages, applies explicit constraints
and readiness rules, selects a provider deterministically, and produces a
version-pinned handoff. Execution and result validation occur only after routing.

FMR is an industry-agnostic router. Industry knowledge belongs in vocabulary
extensions, model-package metadata, provider implementations and validation
specifications. Existing financial models may inform package design and tests;
they do not train or silently influence the deterministic router.

## Terms

**Financial-modelling job** — the provider-neutral statement of an objective,
deliverables, context, available data and assumptions, constraints, requested
outputs and preferred execution mode.

**Model family** — a provider-neutral analytical capability. A family declares
its objective, deliverables, required data and assumptions, checks, supported
extensions and limitations. It contains no workbook coordinates, spreadsheet
formulas, sheet layouts or provider instructions.

**Provider** — a versioned implementation boundary that can execute one or more
model packages or produce a handoff for an external implementation.

**Model package** — a versioned provider offering for a model family. It declares
industry applicability, deliverables, inputs, outputs, checks, capabilities and
limitations. A family being recognized does not make a package executable.

**Source adapter** — a deterministic conversion from an external source into the
canonical financial-data layer. It contains no provider logic or routing policy.

**Provider adapter** — a deterministic conversion from canonical data into one
package's input contract. It contains no source-specific extraction or routing
policy.

**Route decision** — a non-executing, reproducible selection result containing
the chosen family, provider and package, all candidate evaluations, rejection
reasons, missing requirements, fallbacks and the routing-policy version.

**Provider handoff** — the immutable bridge between routing and execution. It
pins the job, decision, provider, package, normalized inputs, configuration,
expected outputs, validation requirements, hashes and unresolved requirements.

## Ownership

FMR core owns:

- job validation and family classification;
- provider and package discovery;
- hard-constraint enforcement and readiness evaluation;
- deterministic ranking and route policies;
- route decisions, handoff compilation and provider-neutral receipts;
- canonical financial concepts and provenance requirements; and
- provider conformance contracts.

Providers own:

- provider-specific formulas, layouts, coordinates and execution instructions;
- runtime dependencies and network behaviour;
- package-specific input and output formats;
- package execution and provider receipts; and
- package-specific validation implementations and limitations.

The Native XLSX provider owns all workbook inspection, planning, formula, style,
coordinate, mutation, recalculation and workbook-output acceptance behaviour.

## Explicit non-goals

FMR does not provide accounting, tax, legal or investment advice; keep books;
invent missing values or assumptions; train a generative model on submitted
workbooks; guarantee that a recognized family has an executable package; execute
provider code during discovery; silently relax job constraints; silently switch
providers after execution starts; embed secrets or sensitive financial values in
receipts; or make the router core responsible for provider formulas or layouts.

## Compatibility during migration

The pre-1.0 `route`, workbook and financial-data commands remain compatibility
interfaces. Their current modules are classified in [CODE_INVENTORY.md](CODE_INVENTORY.md).
Compatibility is not evidence that workbook behaviour belongs to core. New
workbook-specific capability must be implemented under the Native XLSX provider
boundary; removal of compatibility wrappers requires a documented deprecation.
