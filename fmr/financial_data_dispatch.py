from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fmr.financial_data import (
    build_binding_profile,
    build_mapping_profile,
    compile_input_set_from_binding_plan,
    concept_registry_payload,
    import_statement_csv,
    map_financial_data,
    plan_financial_input_bindings,
    validate_binding_plan,
    validate_financial_data_package,
    validate_mapping_result,
)
from fmr.adapters.sources import import_tabular_source, merge_canonical_data

FINANCIAL_DATA_COMMANDS = {
    "financial-concepts",
    "import-statement-csv",
    "make-financial-mapping-profile",
    "map-financial-data",
    "make-financial-binding-profile",
    "plan-financial-bindings",
    "compile-financial-input-set",
    "validate-financial-package",
    "validate-financial-mapping",
    "validate-financial-binding-plan",
    "import-tabular-source",
    "merge-canonical-data",
}


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_object(path: str) -> dict[str, Any]:
    value = _load(path)
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def _load_array(path: str) -> list[dict[str, Any]]:
    value = _load(path)
    if not isinstance(value, list) or not all(
        isinstance(item, dict) for item in value
    ):
        raise ValueError("JSON root must be an array of objects")
    return value


def _write(payload: dict[str, Any], output: str | None = None) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output:
        Path(output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fmr")
    subparsers = parser.add_subparsers(dest="command", required=True)

    concepts = subparsers.add_parser(
        "financial-concepts",
        help="Print the versioned canonical financial concept registry",
    )
    concepts.add_argument("--output")

    import_csv = subparsers.add_parser(
        "import-statement-csv",
        help="Normalize a provider-neutral statement CSV",
    )
    import_csv.add_argument("csv_file")
    import_csv.add_argument("--output")

    import_tabular = subparsers.add_parser(
        "import-tabular-source", help="Import a CSV or XLSX export through an exact source profile"
    )
    import_tabular.add_argument("profile")
    import_tabular.add_argument("source_file")
    import_tabular.add_argument("--entity-id", required=True)
    import_tabular.add_argument("--entity-name")
    import_tabular.add_argument("--currency", required=True)
    import_tabular.add_argument("--output")

    merge_data = subparsers.add_parser(
        "merge-canonical-data", help="Merge compatible canonical financial-data packages"
    )
    merge_data.add_argument("packages", nargs="+")
    merge_data.add_argument("--assumptions")
    merge_data.add_argument("--output")

    mapping_profile = subparsers.add_parser(
        "make-financial-mapping-profile",
        help="Build a deterministic mapping profile from a JSON rule array",
    )
    mapping_profile.add_argument("rules")
    mapping_profile.add_argument("--name", default="mapping profile")
    mapping_profile.add_argument("--output")

    mapping = subparsers.add_parser(
        "map-financial-data",
        help="Map normalized account rows to canonical concepts",
    )
    mapping.add_argument("package")
    mapping.add_argument("--profile")
    mapping.add_argument("--output")

    binding_profile = subparsers.add_parser(
        "make-financial-binding-profile",
        help="Build a semantic workbook-slot binding profile",
    )
    binding_profile.add_argument("bindings")
    binding_profile.add_argument("--name", default="binding profile")
    binding_profile.add_argument("--output")

    binding = subparsers.add_parser(
        "plan-financial-bindings",
        help="Bind financial concepts and constants to reserved workbook slots",
    )
    binding.add_argument("package")
    binding.add_argument("mapping_result")
    binding.add_argument("binding_profile")
    binding.add_argument("write_plan")
    binding.add_argument("execution_receipt")
    binding.add_argument("--output")

    compile_input = subparsers.add_parser(
        "compile-financial-input-set",
        help="Compile a ready semantic binding plan into workbook-input-set.v1",
    )
    compile_input.add_argument("binding_plan")
    compile_input.add_argument("write_plan")
    compile_input.add_argument("execution_receipt")
    compile_input.add_argument("--output")

    validate_package = subparsers.add_parser(
        "validate-financial-package"
    )
    validate_package.add_argument("package")

    validate_mapping = subparsers.add_parser(
        "validate-financial-mapping"
    )
    validate_mapping.add_argument("mapping_result")
    validate_mapping.add_argument("--package")
    validate_mapping.add_argument("--profile")

    validate_binding = subparsers.add_parser(
        "validate-financial-binding-plan"
    )
    validate_binding.add_argument("binding_plan")
    validate_binding.add_argument("--package")
    validate_binding.add_argument("--mapping-result")
    validate_binding.add_argument("--binding-profile")
    validate_binding.add_argument("--write-plan")
    validate_binding.add_argument("--execution-receipt")
    return parser


def run_financial_data_command(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "financial-concepts":
            _write(concept_registry_payload(), args.output)
            return 0
        if args.command == "import-statement-csv":
            payload = import_statement_csv(
                Path(args.csv_file).read_bytes(),
                source_name=Path(args.csv_file).name,
            )
            _write(payload, args.output)
            return 0
        if args.command == "import-tabular-source":
            source_path = Path(args.source_file)
            payload = import_tabular_source(
                source_path.read_bytes(), _load_object(args.profile),
                source_name=source_path.name, entity_id=args.entity_id,
                entity_name=args.entity_name, currency=args.currency,
            )
            _write(payload, args.output)
            return 0
        if args.command == "merge-canonical-data":
            payload = merge_canonical_data(
                [_load_object(path) for path in args.packages],
                assumptions=_load_object(args.assumptions) if args.assumptions else None,
            )
            _write(payload, args.output)
            return 0
        if args.command == "make-financial-mapping-profile":
            payload = build_mapping_profile(
                _load_array(args.rules),
                name=args.name,
            )
            _write(payload, args.output)
            return 0
        if args.command == "map-financial-data":
            payload = map_financial_data(
                _load_object(args.package),
                profile=(
                    _load_object(args.profile) if args.profile else None
                ),
            )
            _write(payload, args.output)
            return 0
        if args.command == "make-financial-binding-profile":
            payload = build_binding_profile(
                _load_array(args.bindings),
                name=args.name,
            )
            _write(payload, args.output)
            return 0
        if args.command == "plan-financial-bindings":
            payload = plan_financial_input_bindings(
                _load_object(args.package),
                _load_object(args.mapping_result),
                _load_object(args.binding_profile),
                write_plan=_load_object(args.write_plan),
                execution_receipt=_load_object(args.execution_receipt),
            )
            _write(payload, args.output)
            return 0
        if args.command == "compile-financial-input-set":
            payload = compile_input_set_from_binding_plan(
                _load_object(args.binding_plan),
                write_plan=_load_object(args.write_plan),
                execution_receipt=_load_object(args.execution_receipt),
            )
            _write(payload, args.output)
            return 0
        if args.command == "validate-financial-package":
            issues = validate_financial_data_package(
                _load_object(args.package)
            )
        elif args.command == "validate-financial-mapping":
            issues = validate_mapping_result(
                _load_object(args.mapping_result),
                package=(
                    _load_object(args.package) if args.package else None
                ),
                profile=(
                    _load_object(args.profile) if args.profile else None
                ),
            )
        else:
            issues = validate_binding_plan(
                _load_object(args.binding_plan),
                package=(
                    _load_object(args.package) if args.package else None
                ),
                mapping_result=(
                    _load_object(args.mapping_result)
                    if args.mapping_result
                    else None
                ),
                binding_profile=(
                    _load_object(args.binding_profile)
                    if args.binding_profile
                    else None
                ),
                write_plan=(
                    _load_object(args.write_plan)
                    if args.write_plan
                    else None
                ),
                execution_receipt=(
                    _load_object(args.execution_receipt)
                    if args.execution_receipt
                    else None
                ),
            )
        _write({"valid": not issues, "issues": list(issues)})
        return 0 if not issues else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _write({"valid": False, "error": str(exc)})
        return 2


__all__ = ["FINANCIAL_DATA_COMMANDS", "run_financial_data_command"]
