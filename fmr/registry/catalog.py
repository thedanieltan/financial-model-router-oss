from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fmr.registry.providers import ProviderManifest

_TRANSITIONS = {
    "submitted": {"active", "incompatible", "withdrawn"},
    "active": {"deprecated", "incompatible"},
    "deprecated": {"active", "incompatible", "withdrawn"},
    "incompatible": {"submitted", "withdrawn"},
    "withdrawn": set(),
}


class ProviderCatalog:
    """Durable local provider-release catalog with immutable version identities."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def snapshot(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"contract_version": "provider-registry.v1", "releases": []}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("contract_version") != "provider-registry.v1" or not isinstance(payload.get("releases"), list):
            raise ValueError("provider registry is invalid")
        return payload

    def submit(self, manifest_payload: dict[str, Any], conformance: dict[str, Any], package_receipt: dict[str, Any], *, available: bool = True, now: str | None = None) -> dict[str, Any]:
        manifest = ProviderManifest.from_mapping(manifest_payload)
        if conformance.get("contract_version") != "provider-conformance-result.v1" or conformance.get("provider_id") != manifest.provider_id:
            raise ValueError("conformance attestation does not match provider")
        if conformance.get("status") != "passed" or conformance.get("conformance_level") not in {"manifest", "executable"}:
            raise ValueError("only passed conformance attestations can be submitted")
        if package_receipt.get("contract_version") != "provider-sdk-package-result.v1" or package_receipt.get("provider_id") != manifest.provider_id:
            raise ValueError("package receipt does not match provider")
        bundle_sha = package_receipt.get("sha256")
        if not isinstance(bundle_sha, str) or len(bundle_sha) != 64:
            raise ValueError("package receipt SHA-256 is invalid")
        bundle_path = Path(str(package_receipt.get("path", "")))
        if not bundle_path.is_file() or hashlib.sha256(bundle_path.read_bytes()).hexdigest() != bundle_sha:
            raise ValueError("provider bundle is missing or does not match package receipt")
        canonical = json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        conformance_canonical = json.dumps(conformance, sort_keys=True, separators=(",", ":")).encode()
        timestamp = now or _timestamp()
        entry = {
            "provider_id": manifest.provider_id, "version": manifest.version,
            "lifecycle_state": "submitted", "available": available,
            "manifest_sha256": hashlib.sha256(canonical).hexdigest(), "bundle_sha256": bundle_sha,
            "conformance_sha256": hashlib.sha256(conformance_canonical).hexdigest(),
            "conformance_level": conformance["conformance_level"], "conformance_status": "passed",
            "license": manifest.license, "runtime_dependencies": list(manifest.runtime_dependencies),
            "privacy_behavior": list(manifest.privacy_behavior),
            "package_versions": sorted(f"{item.package_id}@{item.version}" for item in manifest.packages),
            "manifest": manifest.to_dict(), "conformance": conformance,
            "created_at": timestamp, "updated_at": timestamp,
        }
        snapshot = self.snapshot()
        for existing in snapshot["releases"]:
            if (existing["provider_id"], existing["version"]) == (manifest.provider_id, manifest.version):
                if existing["manifest_sha256"] == entry["manifest_sha256"] and existing["bundle_sha256"] == bundle_sha and existing["conformance_sha256"] == entry["conformance_sha256"]:
                    return existing
                raise ValueError("provider version already exists with different immutable content")
        snapshot["releases"].append(entry)
        snapshot["releases"].sort(key=lambda item: (item["provider_id"], item["version"]))
        self._write(snapshot)
        return entry

    def transition(self, provider_id: str, version: str, state: str, *, now: str | None = None) -> dict[str, Any]:
        if state not in _TRANSITIONS:
            raise ValueError("unsupported registry lifecycle state")
        snapshot = self.snapshot()
        for entry in snapshot["releases"]:
            if (entry["provider_id"], entry["version"]) == (provider_id, version):
                current = entry["lifecycle_state"]
                if state == current:
                    return entry
                if state not in _TRANSITIONS[current]:
                    raise ValueError(f"registry transition is not allowed: {current} -> {state}")
                if state == "active" and (entry["conformance_level"] != "executable" or not entry["available"]):
                    raise ValueError("only available executable-conformant releases can become active")
                entry["lifecycle_state"] = state
                entry["updated_at"] = now or _timestamp()
                self._write(snapshot)
                return entry
        raise KeyError((provider_id, version))

    def audit(self) -> dict[str, Any]:
        findings = []
        for entry in self.snapshot()["releases"]:
            issues = []
            try:
                manifest = ProviderManifest.from_mapping(entry["manifest"])
                canonical = json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":")).encode()
                if hashlib.sha256(canonical).hexdigest() != entry["manifest_sha256"]:
                    issues.append("manifest_hash_mismatch")
                conformance = entry["conformance"]
                encoded = json.dumps(conformance, sort_keys=True, separators=(",", ":")).encode()
                if hashlib.sha256(encoded).hexdigest() != entry["conformance_sha256"]:
                    issues.append("conformance_hash_mismatch")
                if conformance.get("status") != "passed" or conformance.get("provider_id") != manifest.provider_id:
                    issues.append("invalid_conformance_attestation")
            except (KeyError, ValueError, TypeError):
                issues.append("invalid_manifest")
            if issues:
                findings.append({"provider_id": entry["provider_id"], "version": entry["version"], "issues": issues})
        return {"contract_version": "provider-registry-audit.v1", "status": "passed" if not findings else "failed", "findings": findings}

    def set_availability(self, provider_id: str, version: str, available: bool, *, now: str | None = None) -> dict[str, Any]:
        if not isinstance(available, bool):
            raise ValueError("availability must be a boolean")
        snapshot = self.snapshot()
        for entry in snapshot["releases"]:
            if (entry["provider_id"], entry["version"]) == (provider_id, version):
                entry["available"] = available
                entry["updated_at"] = now or _timestamp()
                self._write(snapshot)
                return entry
        raise KeyError((provider_id, version))

    def reconcile(self, *, now: str | None = None) -> dict[str, Any]:
        findings = {(item["provider_id"], item["version"]): item["issues"] for item in self.audit()["findings"]}
        snapshot = self.snapshot()
        changed = []
        for entry in snapshot["releases"]:
            key = (entry["provider_id"], entry["version"])
            reasons = list(findings.get(key, ()))
            if not entry["available"]:
                reasons.append("runtime_unavailable")
            if reasons and entry["lifecycle_state"] in {"submitted", "active", "deprecated"}:
                entry["lifecycle_state"] = "incompatible"
                entry["updated_at"] = now or _timestamp()
                changed.append({"provider_id": key[0], "version": key[1], "reasons": sorted(set(reasons))})
        if changed:
            self._write(snapshot)
        return {"contract_version": "provider-registry-reconciliation.v1", "changed": changed}

    def active_manifests(self) -> tuple[ProviderManifest, ...]:
        audit = self.audit()
        if audit["status"] != "passed":
            raise ValueError("provider registry integrity audit failed")
        return tuple(
            ProviderManifest.from_mapping(entry["manifest"])
            for entry in self.snapshot()["releases"]
            if entry["lifecycle_state"] == "active" and entry["available"]
        )

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
        with tempfile.NamedTemporaryFile(prefix=".fmr-registry-", dir=self.path.parent, delete=False) as handle:
            temporary = Path(handle.name); handle.write(data); handle.flush(); os.fsync(handle.fileno())
        try:
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
