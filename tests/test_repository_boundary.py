from __future__ import annotations

import unittest
from pathlib import Path


class RepositoryBoundaryTests(unittest.TestCase):
    def test_no_spreadsheet_binaries_are_committed(self) -> None:
        root = Path(__file__).resolve().parents[1]
        forbidden = {".xlsx", ".xlsm", ".xlsb", ".xls", ".xltx", ".xltm", ".ods"}
        offenders = [str(path.relative_to(root)) for path in root.rglob("*") if path.is_file() and path.suffix.lower() in forbidden]
        self.assertEqual(offenders, [])

    def test_no_external_repository_urls_in_source_or_docs(self) -> None:
        root = Path(__file__).resolve().parents[1]
        allowed = "https://github.com/thedanieltan/financial-model-router-oss/"
        offenders: list[str] = []
        text_suffixes = {".py", ".json", ".md", ".toml", ".yml", ".yaml", ".txt"}
        for path in list((root / "fmr").rglob("*")) + list((root / "docs").rglob("*")):
            if not path.is_file() or path.suffix.lower() not in text_suffixes:
                continue
            text = path.read_text(encoding="utf-8")
            for line_number, line in enumerate(text.splitlines(), 1):
                if "https://github.com/" in line and allowed not in line:
                    offenders.append(f"{path.relative_to(root)}:{line_number}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
