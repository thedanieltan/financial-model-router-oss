from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

from fmr.financial_data import (
    build_binding_profile,
    build_mapping_profile,
    import_statement_csv,
    map_financial_data,
    plan_financial_input_bindings,
)
from fmr.workbook import execute_workbook_write_plan_bytes
from tests.test_executor import execution_case


def statement_csv_bytes(*, include_unmapped: bool = True) -> bytes:
    stream = io.StringIO(newline="")
    fieldnames = [
        "entity_id",
        "entity_name",
        "currency",
        "period_end",
        "period_type",
        "statement_type",
        "balance_type",
        "account_code",
        "account_name",
        "amount",
        "source_ref",
    ]
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    for year in range(2019, 2026):
        period_end = date(year, 12, 31).isoformat()
        writer.writerow(
            {
                "entity_id": "synthetic-co",
                "entity_name": "Synthetic Company",
                "currency": "USD",
                "period_end": period_end,
                "period_type": "actual",
                "statement_type": "income_statement",
                "balance_type": "flow",
                "account_code": "4000",
                "account_name": "Revenue",
                "amount": str(100 + (year - 2019) * 10),
                "source_ref": f"synthetic:pnl:{year}:revenue",
            }
        )
        writer.writerow(
            {
                "entity_id": "synthetic-co",
                "entity_name": "Synthetic Company",
                "currency": "USD",
                "period_end": period_end,
                "period_type": "actual",
                "statement_type": "income_statement",
                "balance_type": "flow",
                "account_code": "6000",
                "account_name": "Administrative costs",
                "amount": str(40 + (year - 2019) * 4),
                "source_ref": f"synthetic:pnl:{year}:admin-costs",
            }
        )
        if include_unmapped:
            writer.writerow(
                {
                    "entity_id": "synthetic-co",
                    "entity_name": "Synthetic Company",
                    "currency": "USD",
                    "period_end": period_end,
                    "period_type": "actual",
                    "statement_type": "operating_metric",
                    "balance_type": "flow",
                    "account_code": "M001",
                    "account_name": "Support tickets",
                    "amount": str(10 + year - 2019),
                    "source_ref": f"synthetic:metric:{year}:tickets",
                }
            )
    return stream.getvalue().encode("utf-8")


def reserved_records(write_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        record
        for phase in write_plan["phases"]
        for record in phase["records"]
        if record["write_kind"] == "reserve_input"
    ]


def financial_data_case() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    package = import_statement_csv(
        statement_csv_bytes(),
        source_name="synthetic-statements.csv",
    )
    mapping_profile = build_mapping_profile(
        [
            {
                "account_code": "6000",
                "account_name": None,
                "concept_id": "operating_costs",
            }
        ],
        name="synthetic mapping profile",
    )
    mapping_result = map_financial_data(package, profile=mapping_profile)
    source_bytes, write_plan = execution_case()
    execution = execute_workbook_write_plan_bytes(
        source_bytes,
        filename="synthetic.xlsx",
        output_filename="executed.xlsx",
        write_plan=write_plan,
    )
    profile_items: list[dict[str, Any]] = []
    for record in reserved_records(write_plan):
        slot_id = record["slot_id"]
        if slot_id == "volume_driver":
            profile_items.append(
                {
                    "slot_id": slot_id,
                    "source_type": "concept",
                    "concept_id": "revenue",
                    "selector": "period_series",
                }
            )
        elif slot_id == "fixed_cost_driver":
            profile_items.append(
                {
                    "slot_id": slot_id,
                    "source_type": "concept",
                    "concept_id": "operating_costs",
                    "selector": "period_series",
                }
            )
        else:
            profile_items.append(
                {
                    "slot_id": slot_id,
                    "source_type": "constant",
                    "value_type": "number",
                    "value": 1,
                }
            )
    binding_profile = build_binding_profile(
        profile_items,
        name="synthetic budget binding profile",
    )
    binding_plan = plan_financial_input_bindings(
        package,
        mapping_result,
        binding_profile,
        write_plan=write_plan,
        execution_receipt=execution.receipt,
    )
    return (
        package,
        mapping_profile,
        mapping_result,
        binding_profile,
        binding_plan,
        {
            "write_plan": write_plan,
            "execution_receipt": execution.receipt,
            "executed_bytes": execution.output_bytes,
        },
    )
