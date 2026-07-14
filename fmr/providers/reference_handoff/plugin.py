from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from fmr.core.jobs import ModelJob
from fmr.registry import RegisteredPackage


class ReferenceHandoffAdapter:
    def compile(self, job: ModelJob, registered: RegisteredPackage) -> dict[str, Any]:
        return {
            "adapter_id": registered.package.adapter_id,
            "external_request": {
                "objective": job.objective,
                "family": registered.package.model_family,
                "package": registered.package.package_id,
                "input_reference_names": sorted(job.input_references),
            },
        }


class ReferenceHandoffExecutor:
    def execute(self, handoff: dict[str, Any], output_dir: Path, secrets: dict[str, str]) -> dict[str, Any]:
        if secrets:
            raise ValueError("reference-handoff does not accept secrets")
        if handoff.get("provider", {}).get("provider_id") != "reference-handoff" or handoff.get("package", {}).get("package_id") != "reference-handoff/operating-company-dcf":
            raise ValueError("handoff is not assigned to the reference DCF handoff package")
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / "external-provider-handoff.json"
        if output.exists():
            raise ValueError("output path already exists")
        document = {
            "contract_version": "external-provider-handoff.v1",
            "handoff_id": handoff["handoff_id"],
            "handoff_sha256": handoff["handoff_sha256"],
            "provider_payload": handoff["provider_payload"],
            "expected_external_result": "financial_model_result",
        }
        data = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
        with tempfile.NamedTemporaryFile(prefix=".fmr-", suffix=".json", dir=output_dir, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
        try:
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "provider_receipt_version": "reference-handoff-receipt.v1",
            "status": "completed",
            "handoff_sha256": handoff["handoff_sha256"],
            "output_artifacts": [{
                "kind": "external_provider_handoff", "format": "json", "path": str(output),
                "sha256": digest_bytes(data), "size_bytes": len(data),
            }],
            "validation": {"status": "passed", "checks": ["handoff_contract", "atomic_output"]},
        }


def digest_bytes(value: bytes) -> str:
    import hashlib
    return hashlib.sha256(value).hexdigest()
