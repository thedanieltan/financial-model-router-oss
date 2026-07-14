from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fmr.entrypoint import main
from tests.financial_data_case import financial_data_case, statement_csv_bytes


class FinancialDataCliTests(unittest.TestCase):
    def test_import_map_bind_and_compile_commands(self) -> None:
        package, mapping_profile, _, binding_profile, _, execution = (
            financial_data_case()
        )
        del package
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "statements.csv"
            mapping_rules_path = root / "mapping-rules.json"
            binding_rules_path = root / "binding-rules.json"
            package_path = root / "package.json"
            mapping_profile_path = root / "mapping-profile.json"
            mapping_path = root / "mapping.json"
            binding_profile_path = root / "binding-profile.json"
            binding_plan_path = root / "binding-plan.json"
            input_set_path = root / "input-set.json"
            write_plan_path = root / "write-plan.json"
            execution_path = root / "execution.json"

            csv_path.write_bytes(statement_csv_bytes())
            mapping_rules_path.write_text(
                json.dumps(mapping_profile["rules"]), encoding="utf-8"
            )
            binding_rules_path.write_text(
                json.dumps(binding_profile["bindings"]), encoding="utf-8"
            )
            write_plan_path.write_text(
                json.dumps(execution["write_plan"]), encoding="utf-8"
            )
            execution_path.write_text(
                json.dumps(execution["execution_receipt"]), encoding="utf-8"
            )

            self.assertEqual(
                main(
                    [
                        "import-statement-csv",
                        str(csv_path),
                        "--output",
                        str(package_path),
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "make-financial-mapping-profile",
                        str(mapping_rules_path),
                        "--output",
                        str(mapping_profile_path),
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "map-financial-data",
                        str(package_path),
                        "--profile",
                        str(mapping_profile_path),
                        "--output",
                        str(mapping_path),
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "make-financial-binding-profile",
                        str(binding_rules_path),
                        "--output",
                        str(binding_profile_path),
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "plan-financial-bindings",
                        str(package_path),
                        str(mapping_path),
                        str(binding_profile_path),
                        str(write_plan_path),
                        str(execution_path),
                        "--output",
                        str(binding_plan_path),
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "compile-financial-input-set",
                        str(binding_plan_path),
                        str(write_plan_path),
                        str(execution_path),
                        "--output",
                        str(input_set_path),
                    ]
                ),
                0,
            )
            self.assertEqual(
                json.loads(input_set_path.read_text(encoding="utf-8"))[
                    "contract_version"
                ],
                "workbook-input-set.v1",
            )
            self.assertEqual(
                main(
                    [
                        "validate-financial-binding-plan",
                        str(binding_plan_path),
                        "--package",
                        str(package_path),
                        "--mapping-result",
                        str(mapping_path),
                        "--binding-profile",
                        str(binding_profile_path),
                        "--write-plan",
                        str(write_plan_path),
                        "--execution-receipt",
                        str(execution_path),
                    ]
                ),
                0,
            )

    def test_invalid_csv_returns_exit_code_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.csv"
            path.write_text("wrong,columns\n1,2\n", encoding="utf-8")
            self.assertEqual(main(["import-statement-csv", str(path)]), 2)


if __name__ == "__main__":
    unittest.main()
