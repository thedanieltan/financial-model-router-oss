from __future__ import annotations

import unittest

from fmr.workbook import CONTENT_SPECS, COORDINATE_RULES, content_spec_registry_payload


class ContentSpecificationTests(unittest.TestCase):
    def test_registry_covers_every_coordinate_rule(self) -> None:
        self.assertEqual(set(CONTENT_SPECS), set(COORDINATE_RULES))
        registry = content_spec_registry_payload()
        self.assertEqual(
            registry["contract_version"],
            "workbook-content-spec-registry.v1",
        )
        self.assertEqual(len(registry["registry_sha256"]), 64)
        self.assertEqual(len(registry["specifications"]), len(COORDINATE_RULES))

    def test_static_slots_fit_registry_owned_footprints(self) -> None:
        for operation, spec in CONTENT_SPECS.items():
            rule = COORDINATE_RULES[operation]
            if rule.rows is None or rule.columns is None:
                continue
            with self.subTest(operation=operation):
                for slot in spec.slots:
                    self.assertLessEqual(slot.row_offset + slot.row_span, rule.rows)
                    self.assertLessEqual(slot.column_offset + slot.column_span, rule.columns)

    def test_registry_contains_identifiers_not_executable_content(self) -> None:
        registry = content_spec_registry_payload()
        for specification in registry["specifications"]:
            for slot in specification["slots"]:
                if slot["content_kind"] == "label":
                    self.assertIsNotNone(slot["label"])
                else:
                    self.assertIsNotNone(slot["identifier"])
                self.assertNotIn("formula", slot)
                self.assertNotIn("value", slot)
                self.assertNotIn("number_format", slot)


if __name__ == "__main__":
    unittest.main()
