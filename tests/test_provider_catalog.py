from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fmr.registry import ProviderCatalog, ProviderRegistry


class ProviderCatalogTests(unittest.TestCase):
    def _submission(self, root: Path):
        manifest = ProviderRegistry.builtins().providers()[1].to_dict()
        conformance = {
            "contract_version": "provider-conformance-result.v1", "conformance_level": "executable",
            "status": "passed", "provider_id": manifest["provider_id"], "checks": [{"check": "lifecycle", "status": "passed", "details": {}}],
        }
        bundle = root / "provider.zip"
        bundle.write_bytes(b"provider bundle")
        receipt = {
            "contract_version": "provider-sdk-package-result.v1", "provider_id": manifest["provider_id"],
            "path": str(bundle), "sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(), "size_bytes": bundle.stat().st_size, "member_count": 1,
        }
        return manifest, conformance, receipt

    def test_release_identity_is_immutable_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            catalog = ProviderCatalog(Path(temporary) / "registry.json")
            manifest, conformance, receipt = self._submission(Path(temporary))
            entry = catalog.submit(manifest, conformance, receipt, now="2026-01-01T00:00:00Z")
            self.assertEqual(catalog.submit(manifest, conformance, receipt), entry)
            changed = copy.deepcopy(manifest)
            changed["license"] = "different"
            with self.assertRaisesRegex(ValueError, "immutable content"):
                catalog.submit(changed, conformance, receipt)

    def test_lifecycle_requires_executable_available_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            catalog = ProviderCatalog(Path(temporary) / "registry.json")
            manifest, conformance, receipt = self._submission(Path(temporary))
            catalog.submit(manifest, conformance, receipt, available=False)
            with self.assertRaisesRegex(ValueError, "available executable"):
                catalog.transition(manifest["provider_id"], manifest["version"], "active")
            catalog.set_availability(manifest["provider_id"], manifest["version"], True)
            self.assertEqual(catalog.transition(manifest["provider_id"], manifest["version"], "active")["lifecycle_state"], "active")
            self.assertEqual(catalog.transition(manifest["provider_id"], manifest["version"], "deprecated")["lifecycle_state"], "deprecated")
            with self.assertRaisesRegex(ValueError, "not allowed"):
                catalog.transition(manifest["provider_id"], manifest["version"], "submitted")

    def test_audit_detects_tampering_without_executing_provider_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            catalog = ProviderCatalog(Path(temporary) / "registry.json")
            manifest, conformance, receipt = self._submission(Path(temporary))
            catalog.submit(manifest, conformance, receipt)
            self.assertEqual(catalog.audit()["status"], "passed")
            payload = catalog.snapshot()
            payload["releases"][0]["manifest"]["license"] = "tampered"
            catalog.path.write_text(json.dumps(payload), encoding="utf-8")
            audit = catalog.audit()
            self.assertEqual(audit["findings"][0]["issues"], ["manifest_hash_mismatch"])
            with self.assertRaisesRegex(ValueError, "integrity audit failed"):
                catalog.active_manifests()

    def test_reconciliation_marks_unavailable_release_and_active_only_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = ProviderCatalog(root / "registry.json")
            manifest, conformance, receipt = self._submission(root)
            catalog.submit(manifest, conformance, receipt)
            catalog.transition(manifest["provider_id"], manifest["version"], "active")
            self.assertEqual(len(catalog.active_manifests()), 1)
            catalog.set_availability(manifest["provider_id"], manifest["version"], False)
            result = catalog.reconcile(now="2026-01-01T00:00:00Z")
            self.assertEqual(result["changed"][0]["reasons"], ["runtime_unavailable"])
            self.assertEqual(catalog.active_manifests(), ())


if __name__ == "__main__":
    unittest.main()
