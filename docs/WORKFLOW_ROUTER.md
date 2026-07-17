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

## Direct financial source intake

The practitioner workbench can prepare a workflow source from the controlled statement CSV format:

1. download the statement CSV template;
2. upload completed statements;
3. supply explicit assumption values;
4. optionally add exact account mapping rules and operating-driver series;
5. review unmapped-row warnings; and
6. build the workflow with the resulting immutable canonical reference.

The source pipeline is:

```text
statement CSV
→ strict row and entity validation
→ exact built-in aliases plus explicit mapping rules
→ canonical-financial-data.v2
→ immutable local file named by SHA-256
→ finance-workflow-request.v1
```

FMR never fuzzy-maps an account, fills a missing mapped period with zero, or includes unmapped rows in canonical concepts. Unmapped rows remain warnings. Ambiguous, shape-invalid and incomplete mapped series fail closed.

The workflow-source response contains entity, period, mapping and readiness metadata, but not financial values. The canonical values remain in the local hash-pinned source file used by providers.

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
from fmr.financial_data import create_statement_csv_workflow_source
from fmr.workflow import compile_workflow, execute_workflow, workflow_rerun_plan

source = create_statement_csv_workflow_source(
    open("statements.csv", "rb").read(),
    source_name="statements.csv",
    mapping_rules=[],
    assumptions={"forecast_horizon": 3},
)

request["input_references"] = {
    "canonical_financial_data": source["canonical_reference"]
}
request["available_data"] = source["available_data"]
request["available_assumptions"] = source["available_assumptions"]
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

- `GET /api/v2/workflow-sources/statement-csv-template`
- `POST /api/v2/workflow-sources/statement-csv`
- `GET /api/v2/workflows/blueprints`
- `POST /api/v2/workflows/plans`
- `POST /api/v2/workflows/reruns`
- `POST /api/v2/workflows/executions`
- `POST /api/v2/workflows/acceptance`

The browser workbench provides role, objective, statement-source and assumption fields. The compiled result shows the selected blueprint, ordered steps, route decisions, blockers and approval gates.

## Testing and acceptance

The bundled workflow corpus covers supported and intentionally unsupported practitioner workflows. Tests verify:

- deterministic source compilation and immutable storage;
- exact mappings and visible unmapped rows;
- source-to-workflow-to-provider continuity;
- deterministic plans and hashes;
- acyclic dependency graphs;
- exact step order;
- real lower-level route decisions;
- honest blocking for absent model families;
- dependency-based partial reruns;
- Python, CLI and HTTP parity;
- real Python Forecast execution inside workflows; and
- separate implementation, practitioner, deployment and production acceptance gates.

Synthetic acceptance proves implementation behaviour only. Representative anonymized cases and external practitioner reviews remain required before production acceptance.
