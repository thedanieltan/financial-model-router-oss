from __future__ import annotations

from pathlib import Path
from typing import Any

from fmr.core.jobs import ModelJob
from fmr.registry import RegisteredPackage


class NativeXlsxBudgetAdapter:
    def compile(self, job: ModelJob, registered: RegisteredPackage) -> dict[str, Any]:
        reference = job.input_references.get("canonical_financial_data")
        if not isinstance(reference, dict):
            raise ValueError("Native XLSX requires input_references.canonical_financial_data")
        return {
            "adapter_id": registered.package.adapter_id,
            "canonical_financial_data": reference,
            "requested_output_formats": list(job.output_formats),
            "output_basename": "budget-forecast",
        }


class NativeXlsxExecutor:
    def execute(self, handoff: dict[str, Any], output_dir: Path, secrets: dict[str, str]) -> dict[str, Any]:
        if secrets:
            raise ValueError("Native XLSX does not accept secrets")
        if handoff.get("provider", {}).get("provider_id") != "native-xlsx" or handoff.get("package", {}).get("package_id") != "native-xlsx/generic-budget-forecast":
            raise ValueError("handoff is not assigned to the Native XLSX budget package")
        from fmr.providers.native_xlsx.provider import execute_budget_forecast_handoff
        return execute_budget_forecast_handoff(handoff, output_dir)
