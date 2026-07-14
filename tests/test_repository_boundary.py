from __future__ import annotations

import ast
import importlib
import re
import tomllib
import unittest
from pathlib import Path


class RepositoryBoundaryTests(unittest.TestCase):
    def test_financial_data_wheel_check_tracks_project_version(self) -> None:
        root = Path(__file__).resolve().parents[1]
        project_version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        workflow = (root / ".github" / "workflows" / "financial-data-ci.yml").read_text(encoding="utf-8")
        match = re.search(r'assert fmr\.__version__ == "([^"]+)"', workflow)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), project_version)

    def test_target_architecture_namespaces_exist(self) -> None:
        root = Path(__file__).resolve().parents[1] / "fmr"
        required = (
            "core",
            "registry",
            "data",
            "adapters/sources",
            "providers/native_xlsx",
            "sdk",
            "contracts",
        )
        missing = [name for name in required if not (root / name).is_dir()]
        self.assertEqual(missing, [])

    def test_router_core_does_not_import_provider_or_spreadsheet_code(self) -> None:
        core = Path(__file__).resolve().parents[1] / "fmr" / "core"
        forbidden_modules = (
            "fmr.workbook",
            "fmr.providers",
            "openpyxl",
            "libreoffice",
        )
        offenders: list[str] = []
        for path in core.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
            if any(
                imported == forbidden or imported.startswith(forbidden + ".")
                for imported in imports
                for forbidden in forbidden_modules
            ):
                offenders.append(str(path.relative_to(core.parent.parent)))
        self.assertEqual(offenders, [])

    def test_native_xlsx_runtime_is_physically_provider_owned(self) -> None:
        package = Path(__file__).resolve().parents[1] / "fmr"
        implementation = package / "providers" / "native_xlsx" / "workbook"
        compatibility = package / "workbook"
        implementation_modules = {path.name for path in implementation.glob("*.py")}
        compatibility_modules = {path.name for path in compatibility.glob("*.py")}
        self.assertEqual(compatibility_modules, implementation_modules)

        for path in implementation.glob("*.py"):
            self.assertNotIn("fmr.workbook", path.read_text(encoding="utf-8"), path.name)
        for path in compatibility.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            definitions = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]
            self.assertEqual(definitions, [], path.name)
            imports = [node.module for node in tree.body if isinstance(node, ast.ImportFrom)]
            self.assertTrue(imports)
            self.assertTrue(all(module and module.startswith("fmr.providers.native_xlsx.workbook") for module in imports), path.name)

    def test_legacy_workbook_exports_are_provider_object_aliases(self) -> None:
        legacy = importlib.import_module("fmr.workbook")
        provider = importlib.import_module("fmr.providers.native_xlsx.workbook")
        self.assertEqual(legacy.__all__, provider.__all__)
        for name in provider.__all__:
            self.assertIs(getattr(legacy, name), getattr(provider, name), name)

    def test_native_xlsx_contracts_are_authoritative_and_legacy_copies_match(self) -> None:
        package = Path(__file__).resolve().parents[1] / "fmr"
        provider_contracts = package / "providers" / "native_xlsx" / "contracts"
        compatibility_contracts = package / "contracts"
        names = {path.name for path in compatibility_contracts.glob("workbook*.schema.json")}
        names.add("external-calculation-acceptance-request.v1.schema.json")
        self.assertTrue(names)
        self.assertEqual(names, {path.name for path in provider_contracts.glob("*.schema.json")})
        for name in names:
            self.assertEqual((provider_contracts / name).read_bytes(), (compatibility_contracts / name).read_bytes(), name)

    def test_no_spreadsheet_binaries_are_committed(self) -> None:
        root = Path(__file__).resolve().parents[1]
        forbidden = {".xlsx", ".xlsm", ".xlsb", ".xls", ".xltx", ".xltm", ".ods"}
        offenders = [
            str(path.relative_to(root))
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in forbidden
        ]
        self.assertEqual(offenders, [])

    def test_no_external_repository_urls_in_public_text(self) -> None:
        root = Path(__file__).resolve().parents[1]
        github_prefix = "https://" + "github.com/"
        allowed = github_prefix + "thedanieltan/financial-model-router-oss/"
        ignored_parts = {".git", ".venv", "build", "dist", "__pycache__"}
        text_suffixes = {
            ".py",
            ".json",
            ".md",
            ".toml",
            ".yml",
            ".yaml",
            ".txt",
            ".html",
            ".js",
            ".css",
        }
        offenders: list[str] = []
        for path in root.rglob("*"):
            if (
                not path.is_file()
                or path.suffix.lower() not in text_suffixes
                or ignored_parts.intersection(path.parts)
            ):
                continue
            text = path.read_text(encoding="utf-8")
            for line_number, line in enumerate(text.splitlines(), 1):
                if github_prefix in line and allowed not in line:
                    offenders.append(f"{path.relative_to(root)}:{line_number}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
