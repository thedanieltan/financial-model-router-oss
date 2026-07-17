# WP-FMR-PUX-32 — GitHub Pages practitioner demo

## Objective

Publish a no-install public demo that lets practitioners inspect genuine FMR workflow compilation, provider routing, honest blocking and JSON model execution without operating the local developer workbench.

## Implemented

- static GitHub Pages interface for four practitioner cases;
- editable assumptions for forecast, DCF and debt-capacity workflows;
- Pyodide Web Worker with a version-pinned runtime;
- the repository's built wheel installed directly in the browser;
- actual `create_statement_csv_workflow_source` and `compile_workflow` calls;
- actual provider selection and `prepare_handoff` compilation;
- browser-compatible execution of the selected built-in `PythonForecastExecutor`;
- synthetic statement, driver and assumption package;
- actual Python Forecast JSON-provider artifacts;
- explicit unsupported project-finance case;
- privacy, advice and production-acceptance boundaries;
- deterministic site build and GitHub Pages deployment workflow;
- static, runtime, route, provider-execution and unsupported-case tests.

## Browser execution boundary

The normal FMR execution orchestrator isolates providers in a subprocess. Browser WebAssembly cannot spawn that subprocess. The Pages demo therefore preserves the real workflow plan, route decision, selected package, trusted handoff and built-in provider implementation, but invokes the selected Python Forecast executor in-process inside an isolated Web Worker.

This is sufficient for a public implementation demo. It is not equivalent to the local or deployed production execution boundary.

## Data boundary

- The page contains synthetic data only and does not accept user-file uploads.
- Editable assumption values remain inside the browser.
- The page has no FMR application backend and sends no case payload to GitHub.
- The version-pinned Pyodide runtime and the repository wheel are downloaded as static assets.

## Honest limitations

- Native XLSX and LibreOffice paths cannot run on GitHub Pages.
- Browser state is not the persistent local workflow-project store.
- There is no authentication, collaboration or reviewer identity verification.
- The provider subprocess-isolation control is unavailable in browser WebAssembly.
- The page depends on GitHub Pages and the pinned Pyodide CDN.
- Synthetic execution and a successful deployment are implementation evidence, not practitioner or production acceptance.

## Acceptance

- **Implementation:** pending CI.
- **Pages deployment:** pending the first main-branch deployment.
- **Practitioner acceptance:** pending representative external trials.
- **Production acceptance:** not accepted.
