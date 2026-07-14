from __future__ import annotations

from typing import Any

from fmr.core.families import FAMILY_BY_ID
from fmr.registry import ProviderManifest
from fmr.provider_adapters import AVAILABLE_PROVIDER_ADAPTERS


def run_provider_conformance(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    try:
        manifest = ProviderManifest.from_mapping(payload)
        checks.append({"check": "manifest_contract", "status": "passed"})
    except ValueError as exc:
        return {"contract_version": "provider-conformance-result.v1", "status": "failed", "provider_id": payload.get("provider_id"), "checks": [{"check": "manifest_contract", "status": "failed", "reason": str(exc)}]}
    unknown_families = sorted({item.model_family for item in manifest.packages if item.model_family not in FAMILY_BY_ID})
    checks.append({"check": "registered_model_families", "status": "passed" if not unknown_families else "failed", "unknown_families": unknown_families})
    missing_adapters = sorted({item.adapter_id for item in manifest.packages if item.adapter_id not in AVAILABLE_PROVIDER_ADAPTERS})
    checks.append({"check": "installed_provider_adapters", "status": "passed" if not missing_adapters else "failed", "missing_adapters": missing_adapters})
    checks.append({"check": "version_pins", "status": "passed", "provider_version": manifest.version, "package_versions": sorted(f"{item.package_id}@{item.version}" for item in manifest.packages)})
    return {"contract_version": "provider-conformance-result.v1", "status": "passed" if all(item["status"] == "passed" for item in checks) else "failed", "provider_id": manifest.provider_id, "checks": checks}
