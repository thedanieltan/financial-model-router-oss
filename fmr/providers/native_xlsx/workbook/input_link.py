from __future__ import annotations

from typing import Any

from fmr.providers.native_xlsx.workbook.input_population import (
    validate_workbook_input_population_receipt_payload,
)


def validate_input_population_calculation_link(
    population_receipt: Any,
    calculation_acceptance: Any,
) -> tuple[str, ...]:
    """Validate the value-free hash chain from population into calculation."""
    issues: list[str] = []
    population_issues = validate_workbook_input_population_receipt_payload(
        population_receipt
    )
    if population_issues:
        issues.append("input population receipt is invalid")
    if not isinstance(calculation_acceptance, dict):
        issues.append("calculation acceptance must be an object")
        return tuple(dict.fromkeys(issues))
    if (
        calculation_acceptance.get("contract_version")
        != "workbook-calculation-acceptance.v1"
    ):
        issues.append("unsupported calculation acceptance contract_version")
    if isinstance(population_receipt, dict):
        output = population_receipt.get("output")
        calculation_input = calculation_acceptance.get("input")
        if not isinstance(output, dict) or not isinstance(calculation_input, dict):
            issues.append("population output and calculation input must be objects")
        else:
            if output.get("sha256") != calculation_input.get("sha256"):
                issues.append(
                    "calculation input hash does not match population output"
                )
            if output.get("size_bytes") != calculation_input.get("size_bytes"):
                issues.append(
                    "calculation input size does not match population output"
                )
        for field in (
            "write_plan_id",
            "write_plan_sha256",
            "execution_id",
            "execution_receipt_sha256",
        ):
            if population_receipt.get(field) != calculation_acceptance.get(field):
                issues.append(f"{field} does not match calculation acceptance")
    return tuple(dict.fromkeys(issues))


__all__ = ["validate_input_population_calculation_link"]
