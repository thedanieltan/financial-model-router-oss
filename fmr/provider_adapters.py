from __future__ import annotations

from typing import Any

from fmr.core.jobs import ModelJob
from fmr.registry import RegisteredPackage

AVAILABLE_PROVIDER_ADAPTERS = frozenset({
    "native-xlsx/generic-budget-forecast.v1",
    "reference-handoff/generic-budget-forecast.v1",
    "reference-handoff/operating-company-dcf.v1",
})


def compile_provider_payload(job: ModelJob, registered: RegisteredPackage) -> dict[str, Any]:
    adapter_id = registered.package.adapter_id
    common = {
        "adapter_id": adapter_id,
        "objective": job.objective,
        "requested_deliverables": list(job.requested_deliverables),
        "industry": job.industry,
        "input_reference_names": sorted(job.input_references),
        "assumption_keys": list(job.available_assumptions),
        "output_formats": list(job.output_formats),
    }
    if adapter_id == "native-xlsx/generic-budget-forecast.v1":
        reference = job.input_references.get("canonical_financial_data")
        if not isinstance(reference, dict):
            raise ValueError("Native XLSX requires input_references.canonical_financial_data")
        return {**common, "canonical_financial_data": reference, "output_filename": "budget-forecast.xlsx"}
    if adapter_id.startswith("reference-handoff/"):
        return {**common, "external_request": {"family": registered.package.model_family, "package": registered.package.package_id}}
    raise ValueError(f"provider adapter is not installed: {adapter_id}")
