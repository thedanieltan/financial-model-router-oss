from __future__ import annotations

import unittest

from fmr.workbook.operation_specs import OPERATION_SPECS
from fmr.workbook.patch import _OPERATION_SPECS as PATCH_OPERATION_SPECS


class OperationSpecificationTests(unittest.TestCase):
    def test_registry_matches_patch_compiler_mapping(self) -> None:
        self.assertEqual(
            {
                name: (spec.action, spec.semantic_role)
                for name, spec in OPERATION_SPECS.items()
            },
            PATCH_OPERATION_SPECS,
        )

    def test_specification_references_are_unique(self) -> None:
        references = [
            spec.specification_ref for spec in OPERATION_SPECS.values()
        ]
        self.assertEqual(len(references), len(set(references)))


if __name__ == "__main__":
    unittest.main()
