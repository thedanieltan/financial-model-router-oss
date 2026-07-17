# WP-FMR-PUX-31 — Practitioner project lifecycle

## Problem

Practitioners could prepare a financial source and compile a workflow, but the browser journey ended at a technical plan. They could not save the work, reopen it, run ready steps, record approvals and finish later without manually calling the workflow API.

## Outcome

The local practitioner workbench now supports:

1. build a workflow;
2. save it as a named project;
3. run dependency-ready steps;
4. stop at explicit human approval gates;
5. reopen the project later;
6. record approval decisions; and
7. finish the workflow while reusing accepted provider executions.

## Implementation

- WAL-backed SQLite workflow-project store;
- deterministic project identity for a name and workflow-plan hash;
- optimistic project-version checks;
- persistent plan, approval and latest value-free execution receipt;
- append-only project event ledger;
- local managed project output directories;
- project create, list, read, event, approval and execution HTTP endpoints;
- practitioner workbench controls for save, reopen, run and approve;
- provider execution reuse through the existing idempotent execution ledger;
- contract and end-to-end API tests.

## Data boundary

Workflow projects retain:

- the immutable workflow plan;
- canonical source references and hashes;
- assumption names, not assumption values;
- approval decisions;
- provider and workflow receipts; and
- project event metadata.

Financial statement values remain in the separately hash-pinned local canonical source. Provider receipts remain subject to the existing value and secret leakage checks.

## Honest limitations

- local single-host lifecycle only;
- no authentication or multi-user permissions;
- no comments, assignments or reviewer identity verification;
- no cloud synchronization;
- no automated publication of final reports;
- no deployment durability or restore acceptance;
- no practitioner acceptance claim from repository tests.
