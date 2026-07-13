from __future__ import annotations

import csv
import io
from typing import Any

from openpyxl.utils.cell import range_boundaries

from fmr.workbook import (
    compile_workbook_input_set_from_csv,
    execute_workbook_write_plan_bytes,
)
from tests.test_executor import execution_case


def reserved_records(write_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        record
        for phase in write_plan["phases"]
        for record in phase["records"]
        if record["write_kind"] == "reserve_input"
    ]


def cell_count(coordinate: str) -> int:
    min_column, min_row, max_column, max_row = range_boundaries(coordinate)
    return (max_column - min_column + 1) * (max_row - min_row + 1)


def input_csv_bytes(
    write_plan: dict[str, Any],
    *,
    value: int | float | bool = 7,
    value_type: str | None = None,
) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=[
            "record_id",
            "cell_index",
            "value_type",
            "value",
            "source_ref",
        ],
    )
    writer.writeheader()
    selected_type = value_type or ("boolean" if isinstance(value, bool) else "number")
    rendered = (
        "true" if value is True else "false" if value is False else str(value)
    )
    for record in reserved_records(write_plan):
        for index in range(1, cell_count(record["coordinate"]) + 1):
            writer.writerow(
                {
                    "record_id": record["record_id"],
                    "cell_index": index,
                    "value_type": selected_type,
                    "value": rendered,
                    "source_ref": f"synthetic:{record['record_id']}",
                }
            )
    return stream.getvalue().encode("utf-8")


def input_population_case(
    *,
    value: int | float | bool = 7,
) -> tuple[bytes, dict[str, Any], dict[str, Any], dict[str, Any], bytes]:
    source_bytes, write_plan = execution_case()
    execution = execute_workbook_write_plan_bytes(
        source_bytes,
        filename="synthetic.xlsx",
        output_filename="executed.xlsx",
        write_plan=write_plan,
    )
    csv_bytes = input_csv_bytes(write_plan, value=value)
    input_set = compile_workbook_input_set_from_csv(
        csv_bytes,
        source_name="inputs.csv",
        write_plan=write_plan,
        execution_receipt=execution.receipt,
    )
    return (
        execution.output_bytes,
        write_plan,
        execution.receipt,
        input_set,
        csv_bytes,
    )
