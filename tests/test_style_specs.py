from __future__ import annotations

import unittest

from fmr.workbook import (
    CONTENT_SPECS,
    IDENTIFIER_SEMANTIC_TYPES,
    NUMBER_FORMAT_SPECS,
    STYLE_SPECS,
    style_spec_registry_payload,
)


class StyleSpecTests(unittest.TestCase):
    def test_style_registry_covers_all_roles_and_inputs(self) -> None:
        required_roles = {
            slot.format_role for spec in CONTENT_SPECS.values() for slot in spec.slots
        }
        required_inputs = {
            slot.identifier
            for spec in CONTENT_SPECS.values()
            for slot in spec.slots
            if slot.content_kind == "input_placeholder" and slot.identifier is not None
        }
        self.assertTrue(required_roles.issubset(STYLE_SPECS))
        self.assertTrue(required_inputs.issubset(IDENTIFIER_SEMANTIC_TYPES))
        registry = style_spec_registry_payload()
        self.assertEqual(
            registry["contract_version"],
            "workbook-style-spec-registry.v1",
        )
        self.assertEqual(len(registry["registry_sha256"]), 64)
        self.assertEqual(len(registry["role_styles"]), 9)
        self.assertIn("subheader", STYLE_SPECS)

    def test_input_and_output_protection_are_distinct(self) -> None:
        self.assertFalse(STYLE_SPECS["input"].locked)
        self.assertTrue(STYLE_SPECS["output"].locked)
        self.assertEqual(NUMBER_FORMAT_SPECS["percentage"].code, "0.0%;[Red](0.0%);-")
        self.assertEqual(NUMBER_FORMAT_SPECS["currency"].code, "#,##0;[Red](#,##0);-")


if __name__ == "__main__":
    unittest.main()
