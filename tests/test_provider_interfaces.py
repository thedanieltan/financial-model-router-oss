from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from fmr.api.composed import create_app
from fmr.entrypoint import main
from fmr.execution import ExecutionOrchestrator, SqliteExecutionLedger
from fmr.provider_service import prepare_handoff
from tests.test_provider_router import _reference_job


class ProviderInterfaceParityTests(unittest.TestCase):
    def test_top_level_help_lists_provider_lifecycle(self) -> None:
        output = io.StringIO()
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(output):
            main(["--help"])
        self.assertIn("route-job", output.getvalue())

    def test_cli_routes_and_prepares_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, route, handoff = root / "job.json", root / "route.json", root / "handoff.json"
            job.write_text(json.dumps(_reference_job()), encoding="utf-8")
            self.assertEqual(main(["route-job", str(job), "--output", str(route)]), 0)
            self.assertEqual(json.loads(route.read_text())["contract_version"], "route-decision.v2")
            self.assertEqual(main(["prepare-handoff", str(job), "--output", str(handoff)]), 0)
            self.assertEqual(json.loads(handoff.read_text())["contract_version"], "provider-handoff.v1")

    def test_http_and_python_choose_the_same_route(self) -> None:
        from fmr import route_job
        expected = route_job(_reference_job())
        response = TestClient(create_app()).post("/api/v2/jobs/routes", json=_reference_job())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)

    def test_execution_and_strict_validation_have_cli_http_python_parity(self) -> None:
        handoff = prepare_handoff(_reference_job())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            python_result = ExecutionOrchestrator(ledger=SqliteExecutionLedger(root / "python.sqlite3"), managed_output_root=root / "python").execute(handoff, idempotency_key="python", output_dir=root / "python")
            handoff_path, result_path, validation_path = root / "handoff.json", root / "result.json", root / "validation.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            self.assertEqual(main(["execute-job", str(handoff_path), "--idempotency-key", "cli", "--output-dir", str(root / "cli"), "--receipt", str(result_path)]), 0)
            cli_result = json.loads(result_path.read_text())
            self.assertEqual(main(["validate-job-result", str(result_path), "--handoff", str(handoff_path), "--output", str(validation_path)]), 0)
            self.assertTrue(json.loads(validation_path.read_text())["valid"])
            client = TestClient(create_app())
            response = client.post("/api/v2/jobs/executions", json={
                "contract_version": "execution-request.v1", "handoff": handoff, "idempotency_key": "http",
                "execution_mode": "handoff_only", "timeout_seconds": 30, "secret_references": [],
                "output_policy": {"mode": "managed", "overwrite": False, "publish": False},
            })
            self.assertEqual(response.status_code, 200, response.text)
            http_result = response.json()
            validation = client.post("/api/v2/job-results/validate", json={"result": http_result, "handoff": handoff})
            self.assertEqual(validation.status_code, 200)
            self.assertTrue(validation.json()["valid"], validation.json())
            for result in (python_result, cli_result, http_result):
                self.assertEqual(result["state"], "completed")
                self.assertEqual(result["provider"]["provider_id"], "reference-handoff")
                self.assertEqual(result["validation_status"], "passed")

    def test_http_rejects_caller_selected_output_directory(self) -> None:
        handoff = prepare_handoff(_reference_job())
        response = TestClient(create_app()).post("/api/v2/jobs/executions", json={
            "contract_version": "execution-request.v1", "handoff": handoff, "idempotency_key": "unsafe",
            "execution_mode": "handoff_only", "timeout_seconds": 30, "secret_references": [],
            "output_policy": {"mode": "specified_directory", "directory": "/tmp/caller", "overwrite": False, "publish": False},
        })
        self.assertEqual(response.status_code, 422)

    def test_workbench_exposes_provider_candidates(self) -> None:
        client = TestClient(create_app())
        html = client.get("/").text
        javascript = client.get("/assets/provider-routing.js").text
        self.assertIn("Provider routing", html)
        self.assertIn("candidate", html.lower())
        self.assertIn("/api/v2/jobs/routes", javascript)


if __name__ == "__main__":
    unittest.main()
