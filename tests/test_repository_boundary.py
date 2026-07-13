from __future__ import annotations

import unittest
from pathlib import Path


class RepositoryBoundaryTests(unittest.TestCase):
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
