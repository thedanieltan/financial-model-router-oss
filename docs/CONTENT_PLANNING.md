# Workbook content planning

`workbook-content-plan.v1` assigns symbolic content to ranges already reserved by `workbook-coordinate-plan.v1`.

It does not edit a workbook.

## Inputs

The compiler accepts one validated coordinate plan. It recomputes and pins:

- the coordinate-plan SHA-256;
- the content-specification registry SHA-256; and
- the source workbook identity carried by the coordinate plan.

## Content specification registry

`workbook-content-spec-registry.v1` contains one FMR-owned specification for every approved workbook operation.

A specification may define:

- labels;
- input placeholders;
- symbolic formula identifiers;
- period-header identifiers;
- reference identifiers;
- semantic format roles; and
- validation identifiers.

The registry must cover exactly the same operation set as the coordinate-rule registry.

## Content slots

Every placed slot records:

```json
{
  "slot_id": "a1_revenue_forecast",
  "sheet_name": "Revenue Schedule",
  "sheet_position": 4,
  "coordinate": "B6:J6",
  "content_kind": "formula_identifier",
  "label": null,
  "identifier": "fmr.formula.revenue_forecast.v1",
  "format_role": "output",
  "editable": false
}
```

The identifier names a future formula or validation definition. It is not an Excel expression and cannot be executed.

Reference-only operations have symbolic reference slots with no sheet coordinate.

Operations already satisfied by an existing workbook target receive no new content slots.

## Format roles

Content plans use semantic roles only:

- `section_title`;
- `header`;
- `period`;
- `label`;
- `input`;
- `output`;
- `control`; and
- `reference`.

The plan contains no colours, fonts, borders or number formats. Those require a separate style specification.

## Controls

The compiler:

- rejects invalid coordinate plans;
- keeps every placed slot inside its reserved range;
- uses only FMR-owned labels and identifiers;
- emits no input values;
- emits no formula expressions;
- emits no macros or scripts;
- emits no workbook bytes; and
- supports deterministic recomputation for validation.

`ready_for_executor` means the symbolic content plan is internally complete. `execution_supported_by_this_release` remains `false`.

## CLI

```bash
fmr content-specs --output content-specs.json
fmr plan-content coordinate-plan.json --output content-plan.json
fmr validate-content-plan content-plan.json \
  --coordinate-plan coordinate-plan.json
```

## HTTP

```text
GET  /api/v1/workbook-content-specs
POST /api/v1/workbooks/content-plans
POST /api/v1/workbooks/content-plans/validate
```

The next boundary is formula and style definition. Workbook writing remains unavailable until those registries and the executor have separate acceptance tests.
