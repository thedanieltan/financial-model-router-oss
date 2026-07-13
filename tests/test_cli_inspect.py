from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from fmr.cli import main
from tests.xlsx_factory import financial_workbook


class CliInspectTests(unittest.TestCase):
    def test_inspect_prints_workbook_map(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.xlsx"
            path.write_bytes(financial_workbook())
            stream = StringIO()
            with redirect_stdout(stream):
                code = main(["inspect", str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stream.getvalue())["contract_version"], "workbook-map.v1")

    def test_inspect_writes_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.xlsx"
            output = Path(directory) / "map.json"
            path.write_bytes(financial_workbook())
            code = main(["inspect", str(path), "--output", str(output)])
            payload = json.loads(output.read_text())
        self.assertEqual(code, 0)
        self.assertEqual(payload["source"]["filename"], "model.xlsx")


if __name__ == "__main__":
    unittest.main()
