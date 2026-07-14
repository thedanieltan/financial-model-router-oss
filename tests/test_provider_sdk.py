from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from fmr.registry import ProviderManifest
from fmr.sdk import (
    build_provider_bundle,
    initialize_provider_project,
    validate_provider_project,
    validate_version_transition,
)
from fmr.sdk.cli import main


class ProviderSdkTests(unittest.TestCase):
    def test_scaffold_is_statically_valid_without_importing_plugin_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "provider"
            created = initialize_provider_project(root, "sample-provider")
            self.assertEqual(len(created), 6)
            plugin = root / "src" / "sample_provider" / "plugin.py"
            plugin.write_text("raise RuntimeError('must not import during validation')\n", encoding="utf-8")
            result = validate_provider_project(root)
            self.assertEqual(result["status"], "passed")
            ProviderManifest.from_mapping(json.loads((root / "manifest.json").read_text()))

    def test_scaffold_refuses_invalid_names_and_nonempty_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValueError):
                initialize_provider_project(root / "bad", "Bad Provider")
            occupied = root / "occupied"
            occupied.mkdir()
            (occupied / "mine.txt").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not empty"):
                initialize_provider_project(occupied, "safe-provider")
            self.assertEqual((occupied / "mine.txt").read_text(), "keep")

    def test_project_validation_checks_declared_entry_points(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "provider"
            initialize_provider_project(root, "sample-provider")
            pyproject = root / "pyproject.toml"
            pyproject.write_text(pyproject.read_text().replace("sample-provider-handoff =", "wrong-name =", 1), encoding="utf-8")
            result = validate_provider_project(root)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["checks"][2]["details"]["missing"], ["sample-provider-handoff"])

    def test_bundle_is_deterministic_hash_pinned_and_non_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "provider"
            initialize_provider_project(root, "sample-provider")
            (root / "build" / "generated.txt").parent.mkdir()
            (root / "build" / "generated.txt").write_text("exclude", encoding="utf-8")
            (root / "src" / "sample_provider.egg-info").mkdir()
            (root / "src" / "sample_provider.egg-info" / "PKG-INFO").write_text("exclude", encoding="utf-8")
            first = build_provider_bundle(root, Path(temporary) / "one")
            second = build_provider_bundle(root, Path(temporary) / "two")
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual(first["sha256"], hashlib.sha256(Path(first["path"]).read_bytes()).hexdigest())
            with zipfile.ZipFile(first["path"]) as archive:
                self.assertIn("manifest.json", archive.namelist())
                names = " ".join(archive.namelist())
                self.assertNotIn("build/", names)
                self.assertNotIn(".egg-info", names)
            with self.assertRaisesRegex(ValueError, "already exists"):
                build_provider_bundle(root, Path(temporary) / "one")

    def test_version_rules_reject_breaking_minor_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "provider"
            initialize_provider_project(root, "sample-provider")
            previous = json.loads((root / "manifest.json").read_text())
            current = copy.deepcopy(previous)
            current["version"] = "0.2.0"
            current["packages"][0]["version"] = "0.2.0"
            current["packages"][0]["deliverables"] = ["changed-deliverable"]
            issues = validate_version_transition(current, previous)
            self.assertIn("breaking package contract change requires a major-version bump", issues[0])
            current["version"] = "1.0.0"
            current["packages"][0]["version"] = "1.0.0"
            self.assertEqual(validate_version_transition(current, previous), ())
            prerelease = copy.deepcopy(previous)
            prerelease["version"] = "0.1.0a1"
            current_prerelease = copy.deepcopy(prerelease)
            current_prerelease["version"] = "0.1.0a2"
            self.assertEqual(validate_version_transition(current_prerelease, prerelease), ())

    def test_cli_init_validate_and_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "provider"
            self.assertEqual(main(["init", "sample-provider", str(root)]), 0)
            self.assertEqual(main(["validate", str(root)]), 0)
            receipt = Path(temporary) / "package.json"
            self.assertEqual(main(["package", str(root), "--destination", str(Path(temporary) / "dist"), "--output", str(receipt)]), 0)
            self.assertEqual(json.loads(receipt.read_text())["contract_version"], "provider-sdk-package-result.v1")


if __name__ == "__main__":
    unittest.main()
