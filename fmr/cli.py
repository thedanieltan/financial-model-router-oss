from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fmr.plan import build_plan, validate_plan_payload
from fmr.router import route_request
from fmr.types import ModelRequest
from fmr.workbook import (
    WorkbookAnalysis,
    analyse_workbook_map,
    compile_workbook_patch,
    content_spec_registry_payload,
    coordinate_rule_registry_payload,
    formula_spec_registry_payload,
    inspect_workbook,
    operation_spec_registry_payload,
    plan_workbook_content,
    plan_workbook_coordinates,
    plan_workbook_realization,
    resolve_workbook_patch_targets,
    style_spec_registry_payload,
    validate_workbook_content_plan_payload,
    validate_workbook_coordinate_plan_payload,
    validate_workbook_patch_payload,
    validate_workbook_patch_receipt_payload,
    validate_workbook_realization_plan_payload,
    validate_workbook_target_resolution_payload,
)


def _load_object(path: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return data


def _write(payload: dict[str, Any], output: str | None = None) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if output:
        Path(output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fmr")
    subparsers = parser.add_subparsers(dest="command", required=True)

    route = subparsers.add_parser("route", help="Select a model family and report readiness")
    route.add_argument("request")

    plan = subparsers.add_parser("plan", help="Create a controlled transformation plan")
    plan.add_argument("request")

    validate = subparsers.add_parser("validate-plan", help="Validate a transformation plan")
    validate.add_argument("plan")

    inspect = subparsers.add_parser("inspect", help="Inspect an XLSX workbook without modifying it")
    inspect.add_argument("workbook")
    inspect.add_argument("--output")

    analyse = subparsers.add_parser(
        "analyse-workbook",
        help="Inspect a workbook and enrich a model request with evidence-backed inputs",
    )
    analyse.add_argument("workbook")
    analyse.add_argument("request")
    analyse.add_argument("--output")

    compile_patch = subparsers.add_parser(
        "compile-patch",
        help="Compile workbook-analysis.v1 into a validated workbook-patch.v1 manifest",
    )
    compile_patch.add_argument("analysis")
    compile_patch.add_argument("--output")

    validate_patch = subparsers.add_parser("validate-patch", help="Validate a workbook-patch.v1 manifest")
    validate_patch.add_argument("patch")

    validate_receipt = subparsers.add_parser(
        "validate-patch-receipt",
        help="Validate a workbook-patch-receipt.v1 record",
    )
    validate_receipt.add_argument("receipt")
    validate_receipt.add_argument("--patch")

    operation_specs = subparsers.add_parser(
        "operation-specs",
        help="Print the versioned workbook operation specification registry",
    )
    operation_specs.add_argument("--output")

    resolve_targets = subparsers.add_parser(
        "resolve-targets",
        help="Resolve workbook-patch operations to deterministic workbook targets",
    )
    resolve_targets.add_argument("analysis")
    resolve_targets.add_argument("patch")
    resolve_targets.add_argument("--output")

    validate_resolution = subparsers.add_parser(
        "validate-target-resolution",
        help="Validate and deterministically recompute workbook-target-resolution.v1",
    )
    validate_resolution.add_argument("resolution")
    validate_resolution.add_argument("--analysis", required=True)
    validate_resolution.add_argument("--patch", required=True)

    coordinate_rules = subparsers.add_parser(
        "coordinate-rules",
        help="Print the versioned workbook coordinate rule registry",
    )
    coordinate_rules.add_argument("--output")

    plan_coordinates = subparsers.add_parser(
        "plan-coordinates",
        help="Compile a deterministic workbook-coordinate-plan.v1 document",
    )
    plan_coordinates.add_argument("analysis")
    plan_coordinates.add_argument("patch")
    plan_coordinates.add_argument("resolution")
    plan_coordinates.add_argument("--forecast-period-count", type=int, required=True)
    plan_coordinates.add_argument("--output")

    validate_coordinates = subparsers.add_parser(
        "validate-coordinate-plan",
        help="Validate and deterministically recompute workbook-coordinate-plan.v1",
    )
    validate_coordinates.add_argument("coordinate_plan")
    validate_coordinates.add_argument("--analysis", required=True)
    validate_coordinates.add_argument("--patch", required=True)
    validate_coordinates.add_argument("--resolution", required=True)
    validate_coordinates.add_argument("--forecast-period-count", type=int, required=True)

    content_specs = subparsers.add_parser(
        "content-specs",
        help="Print the versioned workbook content specification registry",
    )
    content_specs.add_argument("--output")

    plan_content = subparsers.add_parser(
        "plan-content",
        help="Compile a deterministic workbook-content-plan.v1 document",
    )
    plan_content.add_argument("coordinate_plan")
    plan_content.add_argument("--output")

    validate_content = subparsers.add_parser(
        "validate-content-plan",
        help="Validate and deterministically recompute workbook-content-plan.v1",
    )
    validate_content.add_argument("content_plan")
    validate_content.add_argument("--coordinate-plan", required=True)

    formula_specs = subparsers.add_parser(
        "formula-specs",
        help="Print the versioned formula and validation specification registry",
    )
    formula_specs.add_argument("--output")

    style_specs = subparsers.add_parser(
        "style-specs",
        help="Print the versioned workbook style and number-format registry",
    )
    style_specs.add_argument("--output")

    plan_realization = subparsers.add_parser(
        "plan-realization",
        help="Bind content slots to formula dependencies and declarative styles",
    )
    plan_realization.add_argument("content_plan")
    plan_realization.add_argument("--output")

    validate_realization = subparsers.add_parser(
        "validate-realization-plan",
        help="Validate and deterministically recompute workbook-realization-plan.v1",
    )
    validate_realization.add_argument("realization_plan")
    validate_realization.add_argument("--content-plan", required=True)

    serve = subparsers.add_parser("serve", help="Run the local developer API and browser workbench")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    return parser


def _serve(host: str, port: int, reload: bool) -> int:
    try:
        import uvicorn
    except ImportError as exc:
        raise ValueError(
            'Developer UI dependencies are missing. Install with: pip install -e ".[dev-ui]"'
        ) from exc
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    uvicorn.run("fmr.api.app:app", host=host, port=port, reload=reload)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "serve":
            return _serve(args.host, args.port, args.reload)
        if args.command == "inspect":
            _write(inspect_workbook(args.workbook).to_dict(), args.output)
            return 0
        if args.command == "analyse-workbook":
            workbook_map = inspect_workbook(args.workbook)
            request = ModelRequest.from_mapping(_load_object(args.request))
            _write(analyse_workbook_map(workbook_map, request).to_dict(), args.output)
            return 0
        if args.command == "compile-patch":
            analysis = WorkbookAnalysis.from_mapping(_load_object(args.analysis))
            patch = compile_workbook_patch(analysis).to_dict()
            issues = validate_workbook_patch_payload(patch)
            if issues:
                raise ValueError(f"compiled patch is invalid: {'; '.join(issues)}")
            _write(patch, args.output)
            return 0
        if args.command == "validate-patch":
            issues = validate_workbook_patch_payload(_load_object(args.patch))
            _write({"valid": not issues, "issues": list(issues)})
            return 0 if not issues else 2
        if args.command == "validate-patch-receipt":
            patch = _load_object(args.patch) if args.patch else None
            issues = validate_workbook_patch_receipt_payload(
                _load_object(args.receipt),
                patch=patch,
            )
            _write({"valid": not issues, "issues": list(issues)})
            return 0 if not issues else 2
        if args.command == "operation-specs":
            _write(operation_spec_registry_payload(), args.output)
            return 0
        if args.command == "resolve-targets":
            analysis = WorkbookAnalysis.from_mapping(_load_object(args.analysis))
            patch = _load_object(args.patch)
            resolution = resolve_workbook_patch_targets(analysis, patch).to_dict()
            issues = validate_workbook_target_resolution_payload(
                resolution,
                analysis=analysis,
                patch=patch,
            )
            if issues:
                raise ValueError(f"compiled target resolution is invalid: {'; '.join(issues)}")
            _write(resolution, args.output)
            return 0
        if args.command == "validate-target-resolution":
            analysis = WorkbookAnalysis.from_mapping(_load_object(args.analysis))
            patch = _load_object(args.patch)
            issues = validate_workbook_target_resolution_payload(
                _load_object(args.resolution),
                analysis=analysis,
                patch=patch,
            )
            _write({"valid": not issues, "issues": list(issues)})
            return 0 if not issues else 2
        if args.command == "coordinate-rules":
            _write(coordinate_rule_registry_payload(), args.output)
            return 0
        if args.command == "plan-coordinates":
            analysis = WorkbookAnalysis.from_mapping(_load_object(args.analysis))
            patch = _load_object(args.patch)
            resolution = _load_object(args.resolution)
            coordinate_plan = plan_workbook_coordinates(
                analysis,
                patch,
                resolution,
                forecast_period_count=args.forecast_period_count,
            )
            issues = validate_workbook_coordinate_plan_payload(
                coordinate_plan,
                analysis=analysis,
                patch=patch,
                target_resolution=resolution,
                forecast_period_count=args.forecast_period_count,
            )
            if issues:
                raise ValueError(f"compiled coordinate plan is invalid: {'; '.join(issues)}")
            _write(coordinate_plan, args.output)
            return 0
        if args.command == "validate-coordinate-plan":
            analysis = WorkbookAnalysis.from_mapping(_load_object(args.analysis))
            patch = _load_object(args.patch)
            resolution = _load_object(args.resolution)
            issues = validate_workbook_coordinate_plan_payload(
                _load_object(args.coordinate_plan),
                analysis=analysis,
                patch=patch,
                target_resolution=resolution,
                forecast_period_count=args.forecast_period_count,
            )
            _write({"valid": not issues, "issues": list(issues)})
            return 0 if not issues else 2
        if args.command == "content-specs":
            _write(content_spec_registry_payload(), args.output)
            return 0
        if args.command == "plan-content":
            coordinate_plan = _load_object(args.coordinate_plan)
            content_plan = plan_workbook_content(coordinate_plan)
            issues = validate_workbook_content_plan_payload(
                content_plan,
                coordinate_plan=coordinate_plan,
            )
            if issues:
                raise ValueError(f"compiled content plan is invalid: {'; '.join(issues)}")
            _write(content_plan, args.output)
            return 0
        if args.command == "validate-content-plan":
            coordinate_plan = _load_object(args.coordinate_plan)
            issues = validate_workbook_content_plan_payload(
                _load_object(args.content_plan),
                coordinate_plan=coordinate_plan,
            )
            _write({"valid": not issues, "issues": list(issues)})
            return 0 if not issues else 2
        if args.command == "formula-specs":
            _write(formula_spec_registry_payload(), args.output)
            return 0
        if args.command == "style-specs":
            _write(style_spec_registry_payload(), args.output)
            return 0
        if args.command == "plan-realization":
            content_plan = _load_object(args.content_plan)
            realization_plan = plan_workbook_realization(content_plan)
            issues = validate_workbook_realization_plan_payload(
                realization_plan,
                content_plan=content_plan,
            )
            if issues:
                raise ValueError(f"compiled realization plan is invalid: {'; '.join(issues)}")
            _write(realization_plan, args.output)
            return 0
        if args.command == "validate-realization-plan":
            content_plan = _load_object(args.content_plan)
            issues = validate_workbook_realization_plan_payload(
                _load_object(args.realization_plan),
                content_plan=content_plan,
            )
            _write({"valid": not issues, "issues": list(issues)})
            return 0 if not issues else 2
        if args.command == "validate-plan":
            issues = validate_plan_payload(_load_object(args.plan))
            _write({"valid": not issues, "issues": list(issues)})
            return 0 if not issues else 2

        request = ModelRequest.from_mapping(_load_object(args.request))
        result = route_request(request) if args.command == "route" else build_plan(request)
        _write(result.to_dict())
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _write({"valid": False, "error": str(exc)})
        return 2
