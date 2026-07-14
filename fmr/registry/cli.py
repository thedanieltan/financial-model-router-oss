from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fmr.registry.catalog import ProviderCatalog


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fmr-registry", description="Maintain an FMR provider registry")
    parser.add_argument("--registry", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("manifest"); submit.add_argument("conformance"); submit.add_argument("package_receipt")
    submit.add_argument("--unavailable", action="store_true")
    commands.add_parser("list")
    transition = commands.add_parser("transition")
    transition.add_argument("provider_id"); transition.add_argument("version")
    transition.add_argument("state", choices=("submitted", "active", "deprecated", "incompatible", "withdrawn"))
    availability = commands.add_parser("availability")
    availability.add_argument("provider_id"); availability.add_argument("version")
    availability.add_argument("value", choices=("available", "unavailable"))
    commands.add_parser("audit")
    commands.add_parser("reconcile")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    catalog = ProviderCatalog(args.registry)
    try:
        if args.command == "submit":
            result = catalog.submit(_load(args.manifest), _load(args.conformance), _load(args.package_receipt), available=not args.unavailable)
        elif args.command == "list":
            result = catalog.snapshot()
        elif args.command == "transition":
            result = catalog.transition(args.provider_id, args.version, args.state)
        elif args.command == "availability":
            result = catalog.set_availability(args.provider_id, args.version, args.value == "available")
        elif args.command == "audit":
            result = catalog.audit()
        else:
            result = catalog.reconcile()
        _write(result)
        return 0 if result.get("status") != "failed" else 2
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        _write({"error": str(exc)})
        return 2


def _load(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object")
    return payload


def _write(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
