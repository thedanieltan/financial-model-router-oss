from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fmr.plan import build_plan, validate_plan_payload
from fmr.router import route_request
from fmr.types import ModelRequest


def _load_object(path: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return data


def _write(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fmr")
    subparsers = parser.add_subparsers(dest="command", required=True)
    route = subparsers.add_parser("route", help="Select a model family and report readiness")
    route.add_argument("request")
    plan = subparsers.add_parser("plan", help="Create a controlled transformation plan")
    plan.add_argument("request")
    validate = subparsers.add_parser("validate-plan", help="Validate a transformation plan")
    validate.add_argument("plan")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-plan":
            payload = _load_object(args.plan)
            issues = validate_plan_payload(payload)
            _write({"valid": not issues, "issues": list(issues)})
            return 0 if not issues else 2
        request = ModelRequest.from_mapping(_load_object(args.request))
        if args.command == "route":
            _write(route_request(request).to_dict())
        elif args.command == "plan":
            _write(build_plan(request).to_dict())
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _write({"valid": False, "error": str(exc)})
        return 2
