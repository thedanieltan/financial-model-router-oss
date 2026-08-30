from __future__ import annotations

import argparse
import json
from pathlib import Path

from fmr.providers.native_xlsx.workbook.formula_plan import plan_monthly_fpa_formula_file
from fmr.providers.native_xlsx.workbook.semantic import map_workbook_semantics


SEMANTIC_COMMANDS = {"semantic-map", "formula-plan"}


def run_semantic_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="fmr")
    subparsers = parser.add_subparsers(dest="command", required=True)
    semantic = subparsers.add_parser(
        "semantic-map",
        help="Map financial meaning and formula lineage in an XLSX workbook without modifying it",
    )
    semantic.add_argument("workbook")
    semantic.add_argument("--output")

    formula_plan = subparsers.add_parser(
        "formula-plan",
        help="Create a dry-run monthly FP&A formula-extension plan without modifying the workbook",
    )
    formula_plan.add_argument("workbook")
    formula_plan.add_argument("--output")

    args = parser.parse_args(argv)
    try:
        if args.command == "semantic-map":
            payload = map_workbook_semantics(args.workbook)
        else:
            payload = plan_monthly_fpa_formula_file(args.workbook)
        rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if args.output:
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 2


__all__ = ["SEMANTIC_COMMANDS", "run_semantic_command"]
