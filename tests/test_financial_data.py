from __future__ import annotations

import copy
import unittest

from fmr.financial_data import (
    build_binding_profile,
    build_mapping_profile,
    compile_input_set_from_binding_plan,
    concept_registry_payload,
    import_statement_csv,
    map_financial_data,
    plan_financial_input_bindings,
    validate_binding_plan,
    validate_financial_data_package,
    validate_mapping_profile,
    validate_mapping_result,
)
from fmr.workbook import validate_workbook_input_set_payload
from tests.financial_data_case import (
    financial_data_case,
    reserved_records,
    statement_csv_bytes,
)


class FinancialDataIntakeTests(unittest.TestCase):
    def test_statement_csv_import_is_deterministic_and_value_preserving(self) -> None:
        csv_bytes = statement_csv_bytes()
        package = import_statement_csv(
            csv_bytes,
            source_name="synthetic-statements.csv",
        )
        repeated = import_statement_csv(
            csv_bytes,
            source_name="synthetic-statements.csv",
        )
        self.assertEqual(package, repeated)
        self.assertEqual(validate_financial_data_package(package), ())
        self.assertEqual(package["entity"]["currency"], "USD")
        self.assertEqual(len(package["periods"]), 7)
        self.assertEqual(len(package["rows"]), 3)
        self.assertTrue(
            all(
                isinstance(value["amount"], str)
                for row in package["rows"]
                for value in row["values"]
            )
        )

    def test_statement_csv_rejects_duplicate_period_and_entity_drift(self) -> None:
        csv_text = statement_csv_bytes().decode("utf-8")
        lines = csv_text.splitlines()
        duplicate = ("\n".join([*lines, lines[1]]) + "\n").encode("utf-8")
        with self.assertRaisesRegex(ValueError, "duplicates an account-period"):
            import_statement_csv(duplicate, source_name="duplicate.csv")

        drift = csv_text.replace("synthetic-co", "other-co", 1)
        with self.assertRaisesRegex(ValueError, "exactly one entity"):
            import_statement_csv(drift.encode("utf-8"), source_name="drift.csv")

    def test_exact_aliases_and_explicit_overrides_produce_auditable_mapping(self) -> None:
        package, profile, mapping, _, _, _ = financial_data_case()
        self.assertEqual(validate_mapping_profile(profile), ())
        self.assertEqual(
            validate_mapping_result(
                mapping,
                package=package,
                profile=profile,
            ),
            (),
        )
        mapped = {
            item["row_id"]: item for item in mapping["row_mappings"]
        }
        revenue_row = next(
            row for row in package["rows"] if row["account_name"] == "Revenue"
        )
        cost_row = next(
            row
            for row in package["rows"]
            if row["account_name"] == "Administrative costs"
        )
        metric_row = next(
            row
            for row in package["rows"]
            if row["account_name"] == "Support tickets"
        )
        self.assertEqual(mapped[revenue_row["row_id"]]["concept_id"], "revenue")
        self.assertEqual(
            mapped[revenue_row["row_id"]]["method"],
            "built_in_exact_alias",
        )
        self.assertEqual(
            mapped[cost_row["row_id"]]["concept_id"],
            "operating_costs",
        )
        self.assertEqual(
            mapped[cost_row["row_id"]]["method"],
            "profile_account_code",
        )
        self.assertEqual(mapped[metric_row["row_id"]]["status"], "unmapped")
        self.assertTrue(mapping["ready_for_binding"])
        self.assertEqual(mapping["blockers"], [])

    def test_conflicting_mapping_rules_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "multiple concepts"):
            build_mapping_profile(
                [
                    {
                        "account_code": "4000",
                        "account_name": None,
                        "concept_id": "revenue",
                    },
                    {
                        "account_code": "4000",
                        "account_name": None,
                        "concept_id": "operating_costs",
                    },
                ]
            )

    def test_binding_plan_uses_slot_ids_and_compiles_governed_input_set(self) -> None:
        package, profile, mapping, binding_profile, binding_plan, execution = (
            financial_data_case()
        )
        del profile
        self.assertEqual(
            validate_binding_plan(
                binding_plan,
                package=package,
                mapping_result=mapping,
                binding_profile=binding_profile,
                write_plan=execution["write_plan"],
                execution_receipt=execution["execution_receipt"],
            ),
            (),
        )
        self.assertTrue(binding_plan["ready_for_input_set"])
        self.assertEqual(binding_plan["unresolved_records"], [])
        self.assertEqual(
            [item["slot_id"] for item in binding_plan["bound_records"]],
            [
                record["slot_id"]
                for record in reserved_records(execution["write_plan"])
            ],
        )
        input_set = compile_input_set_from_binding_plan(
            binding_plan,
            write_plan=execution["write_plan"],
            execution_receipt=execution["execution_receipt"],
        )
        self.assertEqual(
            validate_workbook_input_set_payload(
                input_set,
                write_plan=execution["write_plan"],
                execution_receipt=execution["execution_receipt"],
            ),
            (),
        )
        self.assertTrue(
            input_set["source"]["reference"].startswith(
                "financial-data-binding-plan:"
            )
        )

    def test_missing_semantic_slot_binding_blocks_input_set(self) -> None:
        package, _, mapping, binding_profile, _, execution = financial_data_case()
        incomplete = build_binding_profile(
            binding_profile["bindings"][:-1],
            name="incomplete profile",
        )
        binding_plan = plan_financial_input_bindings(
            package,
            mapping,
            incomplete,
            write_plan=execution["write_plan"],
            execution_receipt=execution["execution_receipt"],
        )
        self.assertFalse(binding_plan["ready_for_input_set"])
        self.assertEqual(len(binding_plan["unresolved_records"]), 1)
        self.assertIn("binding_profile_missing_slot", binding_plan["blockers"][0])
        with self.assertRaisesRegex(ValueError, "not ready"):
            compile_input_set_from_binding_plan(
                binding_plan,
                write_plan=execution["write_plan"],
                execution_receipt=execution["execution_receipt"],
            )

    def test_contract_ids_detect_tampering(self) -> None:
        package, _, mapping, binding_profile, binding_plan, execution = (
            financial_data_case()
        )
        altered = copy.deepcopy(package)
        altered["entity"]["currency"] = "SGD"
        self.assertIn(
            "package_id does not match payload",
            validate_financial_data_package(altered),
        )
        altered_mapping = copy.deepcopy(mapping)
        altered_mapping["ready_for_binding"] = False
        self.assertTrue(validate_mapping_result(altered_mapping, package=package))
        altered_binding = copy.deepcopy(binding_plan)
        altered_binding["bound_records"][0]["values"][0] = 999
        self.assertIn(
            "binding_plan_id does not match payload",
            validate_binding_plan(
                altered_binding,
                package=package,
                mapping_result=mapping,
                binding_profile=binding_profile,
                write_plan=execution["write_plan"],
                execution_receipt=execution["execution_receipt"],
            ),
        )

    def test_concept_registry_is_versioned_and_deterministic(self) -> None:
        registry = concept_registry_payload()
        self.assertEqual(registry, concept_registry_payload())
        self.assertEqual(registry["contract_version"], "financial-concept-registry.v1")
        self.assertIn("revenue", {item["concept_id"] for item in registry["concepts"]})


if __name__ == "__main__":
    unittest.main()
