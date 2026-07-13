from __future__ import annotations

import json
import unittest
from pathlib import Path

from fmr.router import route_request
from fmr.types import ModelRequest

FIXTURES = Path(__file__).parent / "fixtures"


class RouterTests(unittest.TestCase):
    def load(self, name: str) -> ModelRequest:
        return ModelRequest.from_mapping(json.loads((FIXTURES / name).read_text(encoding="utf-8")))

    def test_dcf_request_routes_to_dcf(self) -> None:
        result = route_request(self.load("request-dcf-ready.json"))
        self.assertEqual(result.model_family, "operating_company_dcf")
        self.assertTrue(result.readiness.ready)
        self.assertEqual(result.confidence, "high")

    def test_debt_request_reports_missing_inputs(self) -> None:
        result = route_request(self.load("request-debt-blocked.json"))
        self.assertEqual(result.model_family, "debt_capacity_refinancing")
        self.assertFalse(result.readiness.ready)
        self.assertIn("debt_schedule", result.readiness.missing_data)
        self.assertIn("covenant_thresholds", result.readiness.missing_assumptions)

    def test_unknown_objective_fails_closed(self) -> None:
        request = ModelRequest(objective="write a marketing plan", role="operator", available_data=(), workbook_capabilities=(), assumptions=())
        with self.assertRaises(ValueError):
            route_request(request)


if __name__ == "__main__":
    unittest.main()
