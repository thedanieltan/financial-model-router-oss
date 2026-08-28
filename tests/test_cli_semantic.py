from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from fmr.entrypoint import main
from tests.xlsx_factory import financial_workbook


class CliSemanticMapTests(unittest.TestCase):
    def test_semantic_map_prints_read_only_financial_map(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.xlsx"
            path.write_bytes(financial_workbook(include_chart=False))
            stream = StringIO()
            with redirect_stdout(stream):
                code = main(["semantic-map", str(path)])
        self.assertEqual(code, 0)
        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["contract_version"], "workbook-semantic-map.v1")
        self.assertEqual(payload["source"]["filename"], "model.xlsx")

    def test_semantic_map_writes_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.xlsx"
            output = Path(directory) / "semantic-map.json"
            path.write_bytes(financial_workbook(include_chart=False))
            code = main(["semantic-map", str(path), "--output", str(output)])
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(payload["contract_version"], "workbook-semantic-map.v1")


if __name__ == "__main__":
    unittest.main()
