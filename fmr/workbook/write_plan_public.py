from __future__ import annotations

import hashlib
import json
from typing import Any

from fmr.workbook.write_plan import (
    compile_workbook_write_plan as _compile_unordered,
    validate_workbook_write_context_payload,
    validate_workbook_write_plan_payload as _validate_structure,
)


def compile_workbook_write_plan(
    realization_plan: dict[str, Any],
    write_context: dict[str, Any],
) -> dict[str, Any]:
    payload = _compile_unordered(realization_plan, write_context)
    sequence = 0
    for phase in payload["phases"]:
        for record in phase["records"]:
            sequence += 1
            record["sequence"] = sequence
            record["record_id"] = f"fmrw_{sequence:06d}"
    payload["write_record_count"] = sequence
    payload.pop("write_plan_id", None)
    payload["write_plan_id"] = f"fmrw_{_digest(payload)[:24]}"
    return payload


def validate_workbook_write_plan_payload(
    payload: Any,
    *,
    realization_plan: dict[str, Any] | None = None,
    write_context: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    issues = list(_validate_structure(payload))
    if realization_plan is not None and write_context is not None:
        try:
            expected = compile_workbook_write_plan(realization_plan, write_context)
        except ValueError as exc:
            issues.append(f"deterministic recomputation failed: {exc}")
        else:
            if payload != expected:
                issues.append("write plan does not match deterministic recomputation")
    return tuple(dict.fromkeys(issues))


def _digest(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()
