from __future__ import annotations

import json
import unittest
from importlib.resources import files


class ContractTests(unittest.TestCase):
    def test_contracts_are_packaged_and_owned_by_this_repository(self) -> None:
        root = files("fmr.contracts")
        for name in (
            "model-request.v1.schema.json",
            "model-recommendation.v1.schema.json",
            "transformation-plan.v1.schema.json",
            "workbook-map.v1.schema.json",
            "workbook-analysis-request.v1.schema.json",
            "workbook-analysis.v1.schema.json",
            "workbook-patch.v1.schema.json",
            "workbook-patch-receipt.v1.schema.json",
            "workbook-operation-spec-registry.v1.schema.json",
            "workbook-target-resolution-request.v1.schema.json",
            "workbook-target-resolution.v1.schema.json",
        ):
            schema = json.loads(root.joinpath(name).read_text(encoding="utf-8"))
            self.assertTrue(
                schema["$id"].startswith(
                    "https://github.com/thedanieltan/financial-model-router-oss/"
                )
            )


if __name__ == "__main__":
    unittest.main()
