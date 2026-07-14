from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from fmr.adapters.sources import import_tabular_source, merge_canonical_data
from fmr.data import validate_canonical_financial_data
from fmr.entrypoint import main


def _profile(source_type: str, columns: dict[str, str], *, source_system: str = "generic", format: str = "csv", sheet_name: str | None = None) -> dict:
    return {
        "contract_version": "source-adapter-profile.v1",
        "profile_id": f"{source_system}-{source_type}",
        "profile_version": "1.0.0",
        "source_system": source_system,
        "source_type": source_type,
        "format": format,
        "sheet_name": sheet_name,
        "columns": columns,
    }


class SourceAdapterTests(unittest.TestCase):
    def test_imports_exact_financial_statement_csv_with_pinned_provenance(self) -> None:
        content = b"Period,Statement,Concept,Amount\n2025,income_statement,revenue,100\n2026,income_statement,revenue,120\n"
        profile = _profile("financial_statement", {
            "period": "Period", "statement": "Statement", "concept_id": "Concept", "value": "Amount"
        }, source_system="xero")
        result = import_tabular_source(content, profile, source_name="xero-export.csv", entity_id="acme", currency="SGD")
        self.assertEqual(result["financial_statements"]["income_statement"]["revenue"], ["100", "120"])
        self.assertEqual(result["provenance"][0]["source_system"], "xero")
        self.assertEqual(result["provenance"][0]["sha256"], hashlib.sha256(content).hexdigest())
        self.assertEqual(validate_canonical_financial_data(result), ())

    def test_rejects_missing_mapped_header_and_incomplete_series(self) -> None:
        profile = _profile("operational_driver", {"period": "Period", "driver_id": "Driver", "value": "Value"})
        with self.assertRaisesRegex(ValueError, "missing mapped headers"):
            import_tabular_source(b"Period,Driver\n2025,volume\n", profile, source_name="bad.csv", entity_id="acme", currency="SGD")
        content = b"Period,Statement,Concept,Amount\n2025,income_statement,revenue,100\n2026,income_statement,cost,50\n"
        statements = _profile("financial_statement", {"period": "Period", "statement": "Statement", "concept_id": "Concept", "value": "Amount"})
        with self.assertRaisesRegex(ValueError, "missing periods"):
            import_tabular_source(content, statements, source_name="bad.csv", entity_id="acme", currency="SGD")

    def test_trial_balance_and_debt_roll_forward_fail_closed(self) -> None:
        trial = _profile("trial_balance", {
            "period": "Period", "account_code": "Code", "account_name": "Name", "debit": "Debit", "credit": "Credit"
        }, source_system="quickbooks")
        with self.assertRaisesRegex(ValueError, "unbalanced"):
            import_tabular_source(b"Period,Code,Name,Debit,Credit\n2025,1000,Cash,10,0\n", trial, source_name="tb.csv", entity_id="acme", currency="USD")
        debt = _profile("debt_schedule", {
            "facility_id": "Facility", "period": "Period", "opening_balance": "Opening", "drawdown": "Draw", "repayment": "Repay", "interest_rate": "Rate", "interest": "Interest", "closing_balance": "Closing"
        })
        with self.assertRaisesRegex(ValueError, "roll-forward fails"):
            import_tabular_source(b"Facility,Period,Opening,Draw,Repay,Rate,Interest,Closing\nA,2025,100,10,20,.05,5,95\n", debt, source_name="debt.csv", entity_id="acme", currency="SGD")

    def test_xlsx_import_rejects_formulas_in_mapped_fields(self) -> None:
        try:
            from openpyxl import Workbook
        except ImportError:
            self.skipTest("openpyxl is not installed")
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Drivers"
        sheet.append(["Period", "Driver", "Value"])
        sheet.append(["2025", "units", "=1+1"])
        stream = io.BytesIO()
        workbook.save(stream)
        profile = _profile("operational_driver", {"period": "Period", "driver_id": "Driver", "value": "Value"}, format="xlsx", sheet_name="Drivers")
        with self.assertRaisesRegex(ValueError, "unevaluated formula"):
            import_tabular_source(stream.getvalue(), profile, source_name="drivers.xlsx", entity_id="acme", currency="SGD")

    def test_merges_packages_without_inventing_assumptions(self) -> None:
        statement = import_tabular_source(
            b"Period,Statement,Concept,Amount\n2025,income_statement,revenue,100\n2026,income_statement,revenue,120\n",
            _profile("financial_statement", {"period": "Period", "statement": "Statement", "concept_id": "Concept", "value": "Amount"}),
            source_name="statement.csv", entity_id="acme", currency="SGD",
        )
        drivers = import_tabular_source(
            b"Period,Driver,Value\n2025,units,10\n2026,units,12\n",
            _profile("operational_driver", {"period": "Period", "driver_id": "Driver", "value": "Value"}),
            source_name="drivers.csv", entity_id="acme", currency="SGD",
        )
        merged = merge_canonical_data([statement, drivers])
        self.assertEqual(merged["assumptions"], {})
        self.assertEqual(merged["operational_drivers"]["units"], ["10", "12"])
        self.assertEqual(len(merged["provenance"]), 2)

    def test_cli_imports_profiled_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = _profile("operational_driver", {"period": "Period", "driver_id": "Driver", "value": "Value"}, source_system="erpnext")
            (root / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
            (root / "drivers.csv").write_text("Period,Driver,Value\n2025,units,10\n", encoding="utf-8")
            code = main(["import-tabular-source", str(root / "profile.json"), str(root / "drivers.csv"), "--entity-id", "acme", "--currency", "SGD", "--output", str(root / "canonical.json")])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads((root / "canonical.json").read_text())["provenance"][0]["source_system"], "erpnext")


if __name__ == "__main__":
    unittest.main()
