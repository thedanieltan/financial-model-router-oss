from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from fmr import assess_model_intent, create_model_intent, create_scope_confirmation, derive_workbook_scope_evidence
from fmr.api.composed import create_app
from fmr.entrypoint import main
from fmr.providers.native_xlsx.workbook import inspect_workbook_bytes
from tests.xlsx_factory import financial_workbook


def _ready_budget() -> dict:
    return {
        "objective": "Prepare next year's operating budget",
        "decision_context": "operating_plan",
        "requested_outcomes": ["budget", "forecast"],
        "planning_horizon": {"value": 12, "unit": "months"},
        "available_data": ["income_statement_history", "operating_cost_drivers", "revenue_drivers"],
        "available_assumptions": [
            "forecast_horizon", "operating_cost_growth_rate", "revenue_growth_rate",
            "scenario", "scenario_adjustments",
        ],
        "output_formats": ["json"],
    }


class GuidedScopingInterfaceTests(unittest.TestCase):
    def test_cli_exposes_complete_confirmed_scope_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "raw.json"
            intent = root / "intent.json"
            assessment = root / "assessment.json"
            confirmation = root / "confirmation.json"
            job = root / "job.json"
            raw.write_text(json.dumps(_ready_budget()), encoding="utf-8")

            self.assertEqual(main(["create-model-intent", str(raw), "--output", str(intent)]), 0)
            self.assertEqual(main(["assess-scope", str(intent), "--output", str(assessment)]), 0)
            self.assertEqual(main([
                "confirm-scope", str(assessment), "--family", "budget_forecast",
                "--acknowledge", "Not a valuation opinion.", "--output", str(confirmation),
            ]), 0)
            self.assertEqual(main(["compile-scoped-job", str(assessment), str(confirmation), "--output", str(job)]), 0)

            payload = json.loads(job.read_text(encoding="utf-8"))
            self.assertEqual(payload["model_family"], "budget_forecast")
            self.assertEqual(payload["scope_confirmation"]["selected_family"], "budget_forecast")

    def test_cli_answer_command_and_help_are_discoverable(self) -> None:
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()) as output:
            main(["assess-scope", "--help"])
        self.assertIn("intent", output.getvalue())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            intent_path, answered_path = root / "intent.json", root / "answered.json"
            intent_path.write_text(json.dumps(create_model_intent({"objective": "Help me plan"})), encoding="utf-8")
            self.assertEqual(main([
                "answer-scope-question", str(intent_path), "--question", "primary-decision",
                "--answer", "operating_plan", "--output", str(answered_path),
            ]), 0)
            self.assertEqual(json.loads(answered_path.read_text())["decision_context"], "operating_plan")

    def test_http_and_python_scoping_lifecycle_have_parity(self) -> None:
        client = TestClient(create_app())
        expected_intent = create_model_intent(_ready_budget())
        intent_response = client.post("/api/v2/scoping/intents", json=_ready_budget())
        self.assertEqual(intent_response.status_code, 200)
        self.assertEqual(intent_response.json(), expected_intent)

        expected_assessment = assess_model_intent(expected_intent)
        assessment_response = client.post("/api/v2/scoping/assessments", json=expected_intent)
        self.assertEqual(assessment_response.status_code, 200)
        self.assertEqual(assessment_response.json(), expected_assessment)
        candidate = next(item for item in expected_assessment["candidates"] if item["family_id"] == "budget_forecast")
        expected_confirmation = create_scope_confirmation(
            expected_assessment,
            selected_family="budget_forecast",
            acknowledged_limitations=candidate["limitations"],
        )
        confirmation_response = client.post("/api/v2/scoping/confirmations", json={
            "assessment": expected_assessment,
            "selected_family": "budget_forecast",
            "acknowledged_limitations": candidate["limitations"],
        })
        self.assertEqual(confirmation_response.status_code, 200)
        self.assertEqual(confirmation_response.json(), expected_confirmation)
        job_response = client.post("/api/v2/scoping/jobs", json={
            "assessment": expected_assessment,
            "confirmation": expected_confirmation,
        })
        self.assertEqual(job_response.status_code, 200)
        self.assertEqual(job_response.json()["model_family"], "budget_forecast")

    def test_http_questions_knowledge_and_fail_closed_confirmation(self) -> None:
        client = TestClient(create_app())
        knowledge = client.get("/api/v2/scoping/knowledge")
        self.assertEqual(knowledge.status_code, 200)
        self.assertTrue(knowledge.json()["questions"])
        intent = create_model_intent({"objective": "Help me understand this spreadsheet"})
        answer = client.post("/api/v2/scoping/answers", json={
            "intent": intent, "question_id": "primary-decision", "answer": "valuation",
        })
        self.assertEqual(answer.status_code, 200)
        assessment = client.post("/api/v2/scoping/assessments", json=answer.json()).json()
        dcf = next(item for item in assessment["candidates"] if item["family_id"] == "operating_company_dcf")
        self.assertEqual(dcf["suitability"], "blocked")
        rejected = client.post("/api/v2/scoping/confirmations", json={
            "assessment": assessment,
            "selected_family": "operating_company_dcf",
            "acknowledged_limitations": dcf["limitations"],
        })
        self.assertEqual(rejected.status_code, 422)

    def test_workbook_evidence_has_cli_http_python_parity(self) -> None:
        workbook_map = inspect_workbook_bytes(financial_workbook(), filename="synthetic.xlsx").to_dict()
        intent = create_model_intent({"objective": "Help me understand this workbook"})
        expected = derive_workbook_scope_evidence(workbook_map)
        client = TestClient(create_app())
        http_evidence = client.post("/api/v2/scoping/workbook-evidence", json={"workbook_map": workbook_map})
        self.assertEqual(http_evidence.status_code, 200)
        self.assertEqual(http_evidence.json(), expected)
        http_intent = client.post("/api/v2/scoping/workbook-intents", json={
            "intent": intent, "evidence": expected, "workbook_map": workbook_map,
        })
        self.assertEqual(http_intent.status_code, 200)
        self.assertEqual(http_intent.json()["decision_context"], "unknown")
        self.assertEqual(http_intent.json()["available_assumptions"], [])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            map_path, intent_path = root / "map.json", root / "intent.json"
            evidence_path, enriched_path = root / "evidence.json", root / "enriched.json"
            map_path.write_text(json.dumps(workbook_map), encoding="utf-8")
            intent_path.write_text(json.dumps(intent), encoding="utf-8")
            self.assertEqual(main(["derive-workbook-scope-evidence", str(map_path), "--output", str(evidence_path)]), 0)
            self.assertEqual(json.loads(evidence_path.read_text()), expected)
            self.assertEqual(main([
                "apply-workbook-scope-evidence", str(intent_path), str(evidence_path), str(map_path),
                "--output", str(enriched_path),
            ]), 0)
            self.assertEqual(json.loads(enriched_path.read_text()), http_intent.json())

    def test_workbench_is_a_plain_language_confirmed_scope_journey(self) -> None:
        client = TestClient(create_app())
        html = client.get("/").text
        javascript = client.get("/assets/scoping.js").text
        self.assertIn("Guided model scoping", html)
        self.assertIn("What should the model help you decide?", html)
        self.assertIn("Confirm selected scope", html)
        self.assertIn("acknowledged_limitations", javascript)
        self.assertIn("/api/v2/scoping/assessments", javascript)
        self.assertIn("/api/v2/scoping/workbook-evidence", javascript)
        self.assertIn("currentWorkbookMap", javascript)
        self.assertIn("providerJobEditor.value", javascript)


if __name__ == "__main__":
    unittest.main()
