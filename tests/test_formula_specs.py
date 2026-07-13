from __future__ import annotations

import re
import unittest

from fmr.workbook import (
    CONTENT_SPECS,
    FORMULA_SPECS,
    formula_spec_registry_payload,
    resolve_formula_spec,
)


class FormulaSpecTests(unittest.TestCase):
    def test_registry_covers_content_formula_and_validation_identifiers(self) -> None:
        required = {
            slot.identifier
            for spec in CONTENT_SPECS.values()
            for slot in spec.slots
            if slot.content_kind in {"formula_identifier", "validation_identifier"}
            and slot.identifier is not None
        }
        self.assertTrue(required.issubset(FORMULA_SPECS))
        registry = formula_spec_registry_payload()
        self.assertEqual(
            registry["contract_version"],
            "workbook-formula-spec-registry.v1",
        )
        self.assertEqual(registry["expression_language"], "fmr-expression.v1")
        self.assertEqual(len(registry["registry_sha256"]), 64)
        self.assertGreater(len(registry["specifications"]), 40)

    def test_expression_templates_are_coordinate_free_and_non_excel(self) -> None:
        registry = formula_spec_registry_payload()
        a1 = re.compile(r"(?<![A-Za-z0-9_])[A-Z]{1,3}[1-9][0-9]*(?![A-Za-z0-9_])")
        for spec in registry["specifications"]:
            expression = spec["expression_template"]
            self.assertFalse(expression.startswith("="))
            self.assertNotRegex(expression, a1)
            for marker in ("!", "$", "[", "]"):
                self.assertNotIn(marker, expression)
            self.assertEqual(spec["circularity_policy"], "forbid")

    def test_generated_forecast_formula_identifiers_use_pattern_spec(self) -> None:
        first = resolve_formula_spec("fmr.formula.forecast_column_1.v1")
        sixtieth = resolve_formula_spec("fmr.formula.forecast_column_60.v1")
        self.assertEqual(first, sixtieth)
        self.assertEqual(first.formula_kind, "copy_rule")
        self.assertEqual(first.fill_policy, "down_target_range")
        with self.assertRaises(KeyError):
            resolve_formula_spec("fmr.formula.forecast_column_0.v1")


if __name__ == "__main__":
    unittest.main()
