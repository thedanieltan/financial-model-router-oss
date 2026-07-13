from __future__ import annotations

import json
import unittest
from pathlib import Path

from fmr.plan import build_plan, validate_plan_payload
from fmr.types import ModelRequest

FIXTURES = Path(__file__).parent / "fixtures"


class PlanTests(unittest.TestCase):
    def load(self, name: str) -> ModelRequest:
        return ModelRequest.from_mapping(json.loads((FIXTURES / name).read_text(encoding="utf-8")))

    def test_ready_request_has_no_unresolved_inputs(self) -> None:
        plan = build_plan(self.load("request-dcf-ready.json"))
        self.assertTrue(plan.ready_to_apply)
        self.assertFalse(plan.unresolved_inputs)
        self.assertEqual(plan.operations[0].operation, "preserve_existing_workbook")
        self.assertFalse(validate_plan_payload(plan.to_dict()))

    def test_blocked_request_starts_with_input_request(self) -> None:
        plan = build_plan(self.load("request-debt-blocked.json"))
        self.assertFalse(plan.ready_to_apply)
        self.assertEqual(plan.operations[0].operation, "request_missing_inputs")
        self.assertTrue(plan.unresolved_inputs)

    def test_executable_workbook_fields_are_rejected(self) -> None:
        payload = build_plan(self.load("request-dcf-ready.json")).to_dict()
        payload["operations"][0]["formula"] = "=1+1"
        issues = validate_plan_payload(payload)
        self.assertTrue(any("executable workbook fields" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
