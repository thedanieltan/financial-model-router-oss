from __future__ import annotations

import ast
import unittest
from pathlib import Path


class RepositoryBoundaryTests(unittest.TestCase):
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
