from __future__ import annotations

import hashlib
import io
import warnings
import zipfile
import tempfile
import unittest
from pathlib import Path

from fmr.workbook import inspect_workbook, inspect_workbook_bytes
from tests.xlsx_factory import build_xlsx, financial_workbook


class WorkbookInspectionTests(unittest.TestCase):
    def test_financial_workbook_is_mapped(self) -> None:
        data = financial_workbook()
        result = inspect_workbook_bytes(data, filename="synthetic-financial-model.xlsx")
        payload = result.to_dict()
        self.assertEqual(payload["contract_version"], "workbook-map.v1")
        self.assertEqual(payload["workbook"]["sheet_count"], 3)
        self.assertEqual(payload["workbook"]["defined_names"], ["ForecastStart"])
        income = payload["sheets"][0]
        self.assertEqual(income["candidate_role"]["value"], "income_statement")
        self.assertEqual(income["candidate_role"]["confidence"], "high")
        self.assertEqual(income["detected_periods"], ["2024", "2025", "2026E"])
        self.assertEqual(income["formula_cells"], 2)
        self.assertIn("revenue", income["candidate_metrics"])
        self.assertIn("hidden_sheet:Balance Sheet:hidden", payload["findings"])
        self.assertIn("unsupported_feature:charts", payload["findings"])

    def test_unknown_sheet_fails_to_unknown_classification(self) -> None:
        data = build_xlsx([{"name": "Notes", "cells": {"A1": "General notes", "A2": "Nothing financial"}}])
        result = inspect_workbook_bytes(data, filename="notes.xlsx")
        classification = result.sheets[0].candidate_role
        self.assertEqual(classification.value, "unknown")
        self.assertEqual(classification.confidence, "low")

    def test_external_links_are_reported(self) -> None:
        result = inspect_workbook_bytes(financial_workbook(external_link=True), filename="external.xlsx")
        self.assertTrue(result.external_links_detected)
        self.assertGreater(result.sheets[0].external_formula_references, 0)
        self.assertIn("external_links_detected", result.findings)

    def test_source_file_is_not_modified(self) -> None:
        data = financial_workbook()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.xlsx"
            path.write_bytes(data)
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            result = inspect_workbook(path)
            after = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(before, after)
        self.assertEqual(result.source_sha256, before)

    def test_rejects_unsupported_extension(self) -> None:
        with self.assertRaisesRegex(ValueError, "only .xlsx"):
            inspect_workbook_bytes(financial_workbook(), filename="model.xlsm")


    def test_rejects_duplicate_archive_entries(self) -> None:
        source = financial_workbook()
        original = zipfile.ZipFile(io.BytesIO(source))
        output = io.BytesIO()
        with original, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
            for info in original.infolist():
                target.writestr(info.filename, original.read(info.filename))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                target.writestr("xl/workbook.xml", original.read("xl/workbook.xml"))
        with self.assertRaisesRegex(ValueError, "duplicate entries"):
            inspect_workbook_bytes(output.getvalue(), filename="duplicate.xlsx")

    def test_rejects_malformed_archive(self) -> None:
        with self.assertRaisesRegex(ValueError, "valid XLSX archive"):
            inspect_workbook_bytes(b"not-a-zip", filename="broken.xlsx")


if __name__ == "__main__":
    unittest.main()
