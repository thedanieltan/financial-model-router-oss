from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fmr.plan import build_plan, validate_plan_payload
from fmr.router import route_request
from fmr.types import ModelRequest
from fmr.workbook import analyse_workbook_map, inspect_workbook


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

    route = subparsers.add_parser(
        "route",
        help="Select a model family and report readiness",
    )
    route.add_argument("request")

    plan = subparsers.add_parser(
        "plan",
        help="Create a controlled transformation plan",
    )
    plan.add_argument("request")

    validate = subparsers.add_parser(
        "validate-plan",
        help="Validate a transformation plan",
    )
    validate.add_argument("plan")

    inspect = subparsers.add_parser(
        "inspect",
        help="Inspect an XLSX workbook without modifying it",
    )
    inspect.add_argument("workbook")
    inspect.add_argument("--output")

    analyse = subparsers.add_parser(
        "analyse-workbook",
        help="Inspect a workbook and enrich a model request with evidence-backed inputs",
    )
    analyse.add_argument("workbook")
    analyse.add_argument("request")
    analyse.add_argument("--output")

    serve = subparsers.add_parser(
        "serve",
        help="Run the local developer API and browser workbench",
    )
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
