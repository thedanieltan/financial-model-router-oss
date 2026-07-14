from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fmr.sdk.conformance import run_provider_conformance
from fmr.sdk.project import build_provider_bundle, initialize_provider_project, validate_provider_project


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fmr-provider", description="Author and test FMR provider packages")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="scaffold a provider project")
    init.add_argument("provider_id")
    init.add_argument("destination")
    init.add_argument("--force", action="store_true")
    validate = commands.add_parser("validate", help="validate manifests and project metadata without loading provider code")
    validate.add_argument("project")
    validate.add_argument("--previous-manifest")
    validate.add_argument("--output")
    test = commands.add_parser("test", help="run executable conformance using installed entry points")
    test.add_argument("project")
    test.add_argument("--fixture", default="fixtures/model-job.v2.json")
    test.add_argument("--output")
    package = commands.add_parser("package", help="create a deterministic provider submission bundle")
    package.add_argument("project")
    package.add_argument("--destination", default="dist")
    package.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            created = initialize_provider_project(args.destination, args.provider_id, force=args.force)
            _write({"created": [str(path) for path in created]})
            return 0
        if args.command == "validate":
            result = validate_provider_project(args.project, previous_manifest=args.previous_manifest)
            _write(result, args.output)
            return 0 if result["status"] == "passed" else 2
        if args.command == "test":
            root = Path(args.project)
            manifest = json.loads(root.joinpath("manifest.json").read_text(encoding="utf-8"))
            fixture = json.loads(root.joinpath(args.fixture).read_text(encoding="utf-8"))
            result = run_provider_conformance(manifest, fixture)
            _write(result, args.output)
            return 0 if result["status"] == "passed" else 2
        result = build_provider_bundle(args.project, args.destination)
        _write(result, args.output)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _write({"error": str(exc)})
        return 2


def _write(payload: dict[str, Any], output: str | None = None) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output:
        Path(output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    raise SystemExit(main())
