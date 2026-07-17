# Practitioner workflow router

The workflow router sits above FMR's existing model router. A practitioner states the finance work to complete; FMR selects a controlled workflow blueprint, compiles an ordered dependency graph, routes every model step through `model-job.v2`, and keeps missing data, assumptions, approvals and unsupported capabilities explicit.

## Boundary

The workflow router owns:

- practitioner workflow requests;
- deterministic blueprint selection;
- ordered step compilation and dependency validation;
- step-level model jobs and route decisions;
- human approval gates;
- dependency-based partial rerun planning; and
- workflow-level execution receipts.

The existing model router still owns provider and package selection. Providers still own model execution and artifacts. The workflow router does not invent financial assumptions, override provider controls or silently substitute another model family.

## Built-in workflows

The initial registry contains:

- monthly forecast update;
- scenario analysis;
- operating-company valuation;
- debt-capacity refresh;
- project-finance debt sizing;
- leveraged-buyout screening; and
- venture follow-on analysis.

The first four route to currently implemented model families when their data and assumptions are ready. Project-finance, LBO and cap-table workflows compile honestly as blocked until conformant provider packages exist.

## Python

```python
from fmr.workflow import compile_workflow, execute_workflow, workflow_rerun_plan

plan = compile_workflow(request)
rerun = workflow_rerun_plan(plan, ["revenue_growth_rate"])
result = execute_workflow(
    plan,
    idempotency_key="fy27-forecast-v3",
    output_dir="./outputs",
    approvals={"review_forecast": True},
)
```

## CLI

```bash
fmr compile-workflow workflow-request.json --output workflow-plan.json
fmr plan-workflow-rerun workflow-plan.json \
  --changed-input revenue_growth_rate \
  --output rerun-plan.json
fmr execute-workflow workflow-plan.json \
  --idempotency-key fy27-forecast-v3 \
  --output-dir ./outputs \
  --approvals approvals.json \
  --receipt workflow-result.json
```

## HTTP

- `GET /api/v2/workflows/blueprints`
- `POST /api/v2/workflows/plans`
- `POST /api/v2/workflows/reruns`
- `POST /api/v2/workflows/executions`
- `POST /api/v2/workflows/acceptance`

The browser workbench provides role and objective fields plus practitioner examples. The compiled result shows the selected blueprint, ordered steps, route decisions, blockers and approval gates.

## Testing and acceptance

The bundled workflow corpus covers supported and intentionally unsupported practitioner workflows. Tests verify:

- deterministic plans and hashes;
- acyclic dependency graphs;
- exact step order;
- real lower-level route decisions;
- honest blocking for absent model families;
- dependency-based partial reruns;
- Python, CLI and HTTP parity;
- a real DCF provider execution inside the workflow; and
- separate implementation and practitioner acceptance gates.

Synthetic acceptance proves implementation behaviour only. Representative anonymized cases and external practitioner reviews remain required before production acceptance.
