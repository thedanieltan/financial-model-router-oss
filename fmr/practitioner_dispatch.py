from __future__ import annotations

import argparse
import json
from pathlib import Path

from fmr.practitioner.saas_budget import build_saas_budget_workbook_from_payload

PRACTITIONER_COMMANDS = {"saas-budget-workbook"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fmr")
    subparsers = parser.add_subparsers(dest="command", required=True)
    saas = subparsers.add_parser(
        "saas-budget-workbook",
        help="Generate a practitioner SaaS Budget & Forecast XLSX workbook",
    )
    saas.add_argument("--input-json", help="Optional JSON assumptions payload")
    saas.add_argument("--output", required=True, help="Output XLSX path")
    saas.add_argument("--company-name", default="Example SaaS Company")
    saas.add_argument("--currency", default="SGD")
    saas.add_argument("--forecast-months", type=int, default=12)
    saas.add_argument("--opening-arr", type=float, default=1_200_000)
    saas.add_argument("--monthly-new-arr", type=float, default=50_000)
    saas.add_argument("--monthly-expansion-arr", type=float, default=15_000)
    saas.add_argument("--monthly-contraction-arr", type=float, default=5_000)
    saas.add_argument("--monthly-churned-arr", type=float, default=10_000)
    saas.add_argument("--gross-margin-rate", type=float, default=0.80)
    saas.add_argument("--sales-marketing-monthly", type=float, default=80_000)
    saas.add_argument("--rnd-monthly", type=float, default=90_000)
    saas.add_argument("--ga-monthly", type=float, default=50_000)
    saas.add_argument("--starting-cash", type=float, default=1_500_000)
    saas.add_argument("--headcount", type=float, default=25)
    saas.add_argument("--average-salary-per-head-monthly", type=float, default=9_000)
    return parser


def _payload_from_args(args: argparse.Namespace) -> dict[str, object]:
    if args.input_json:
        payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("input JSON root must be an object")
        return payload
    return {
        "company_name": args.company_name,
        "currency": args.currency,
        "forecast_months": args.forecast_months,
        "opening_arr": args.opening_arr,
        "monthly_new_arr": args.monthly_new_arr,
        "monthly_expansion_arr": args.monthly_expansion_arr,
        "monthly_contraction_arr": args.monthly_contraction_arr,
        "monthly_churned_arr": args.monthly_churned_arr,
        "gross_margin_rate": args.gross_margin_rate,
        "sales_marketing_monthly": args.sales_marketing_monthly,
        "rnd_monthly": args.rnd_monthly,
        "ga_monthly": args.ga_monthly,
        "starting_cash": args.starting_cash,
        "headcount": args.headcount,
        "average_salary_per_head_monthly": args.average_salary_per_head_monthly,
    }


def run_practitioner_command(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "saas-budget-workbook":
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            workbook = build_saas_budget_workbook_from_payload(_payload_from_args(args))
            output.write_bytes(workbook)
            print(json.dumps({"valid": True, "output": str(output), "size_bytes": len(workbook)}, indent=2))
            return 0
        raise ValueError(f"unknown practitioner command: {args.command}")
    except Exception as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, indent=2))
        return 2
