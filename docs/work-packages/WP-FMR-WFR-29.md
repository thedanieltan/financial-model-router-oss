# WP-FMR-WFR-29 — Practitioner workflow router

## Problem

Practitioners currently have to translate their work into one model family, prepare technical job contracts and understand provider routing. That does not fit normal finance-manager, FP&A, investment or project-finance workflows.

## Outcome

A new deterministic layer compiles a practitioner objective into an ordered workflow of source validation, model work, review gates and final assembly. Every model step reuses the existing route, handoff and execution integrity chain.

## Implemented slices

1. **Contracts and blueprints**
   - strict workflow request, plan, rerun, execution and acceptance contracts;
   - seven built-in practitioner workflows;
   - graph validation and stable hashes.

2. **Compiler and routing integration**
   - role, objective and output-based blueprint selection;
   - model-job compilation for each model step;
   - actual `route_job` evaluation and explicit missing requirements;
   - unsupported model families remain blocked.

3. **Execution and reruns**
   - dependency-ordered execution through `prepare_handoff` and `ExecutionOrchestrator`;
   - human approval gates;
   - dependency-based invalidation and reusable-step reporting.

4. **Interfaces**
   - Python API;
   - CLI;
   - HTTP endpoints;
   - MCP tools;
   - practitioner-first browser entry point.

5. **Acceptance**
   - synthetic practitioner workflow corpus;
   - schema, deterministic, graph, interface-parity and blocked-capability tests;
   - real Python Forecast DCF execution inside a workflow;
   - separate practitioner-review gate.

## Honest limitations

- project-finance sculpting, LBO and cap-table/dilution packages are not yet implemented;
- the browser can compile a workflow but source-upload-to-canonical-package continuity remains a later integration slice;
- collaboration, persistent workflow projects and production deployment acceptance remain outside this work package;
- synthetic cases do not constitute practitioner acceptance.
