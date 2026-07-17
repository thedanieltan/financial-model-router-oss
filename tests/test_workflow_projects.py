from __future__ import annotations

import json
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from fmr.api import workflow_project_routes
from fmr.api.composed import create_app
from fmr.financial_data import WorkflowSourceStore, create_statement_csv_workflow_source
from fmr.workflow import compile_workflow
from fmr.workflow_projects import WorkflowProjectStore
from tests.financial_data_case import statement_csv_bytes


ASSUMPTIONS = {
    "forecast_horizon": 3,
    "operating_cost_growth_rate": "0.05",
    "revenue_growth_rate": "0.08",
    "scenario": "base",
    "scenario_adjustments": {
        "base": {
            "operating_cost_growth_delta": "0",
            "revenue_growth_delta": "0",
        }
    },
}

MAPPING_RULES = [
    {
        "account_code": "6000",
        "account_name": None,
        "concept_id": "operating_costs",
    }
]


def _plan(root: Path) -> dict:
    source = create_statement_csv_workflow_source(
        statement_csv_bytes(include_unmapped=False),
        source_name="synthetic-statements.csv",
        mapping_rules=MAPPING_RULES,
        assumptions=ASSUMPTIONS,
        store=WorkflowSourceStore(root / "sources"),
    )
    return compile_workflow(
        {
            "contract_version": "finance-workflow-request.v1",
            "objective": "Update the full year forecast using actuals",
            "role": "fp_and_a",
            "entity_id": source["entity"]["entity_id"],
            "reporting_period": source["periods"][-1],
            "requested_outputs": ["rolling_forecast", "management_pack"],
            "available_data": [
                *source["available_data"],
                "operating_cost_drivers",
                "revenue_drivers",
            ],
            "available_assumptions": source["available_assumptions"],
            "input_references": {
                "canonical_financial_data": source["canonical_reference"]
            },
            "industry": None,
            "output_formats": ["json"],
            "policy_name": "json-first",
            "constraints": {
                "local_only": True,
                "open_source_only": True,
                "network_allowed": False,
            },
            "context": {"workflow_source_id": source["source_id"]},
        }
    )


def _model_execution(project: dict) -> dict:
    return next(
        result["execution_result"]
        for result in project["latest_execution"]["step_results"]
        if result["step_id"] == "refresh_forecast"
    )


class WorkflowProjectTests(unittest.TestCase):
    def test_project_persists_and_reopens_without_financial_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = WorkflowProjectStore(
                root / "projects.sqlite3",
                output_root=root / "outputs",
            )
            plan = _plan(root)
            created = store.create("FY2027 rolling forecast", plan)
            repeated = store.create("FY2027 rolling forecast", plan)
            self.assertEqual(created, repeated)
            reopened = WorkflowProjectStore(
                root / "projects.sqlite3",
                output_root=root / "outputs",
            ).get(created["project_id"])
            self.assertEqual(reopened, created)
            serialized = json.dumps(reopened, sort_keys=True)
            self.assertNotIn("financial_statements", serialized)
            self.assertIn("canonical_financial_data", serialized)
            self.assertEqual(store.list()["projects"][0]["project_id"], created["project_id"])

    def test_run_review_and_finish_reuses_provider_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = WorkflowProjectStore(
                root / "projects.sqlite3",
                output_root=root / "outputs",
            )
            created = store.create("Forecast review", _plan(root))
            first = store.execute(created["project_id"], expected_version=1)
            self.assertEqual(first["status"], "awaiting_approval")
            first_execution = _model_execution(first)
            approved = store.set_approvals(
                created["project_id"],
                {"review_forecast": True},
                expected_version=first["version"],
            )
            completed = store.execute(
                created["project_id"],
                expected_version=approved["version"],
            )
            self.assertEqual(completed["status"], "completed")
            second_execution = _model_execution(completed)
            self.assertEqual(
                first_execution["execution_id"],
                second_execution["execution_id"],
            )
            events = store.events(created["project_id"])["events"]
            self.assertEqual(
                [item["detail_code"] for item in events],
                [
                    "plan_saved",
                    "execution_awaiting_approval",
                    "approval_recorded",
                    "execution_completed",
                ],
            )

    def test_unknown_approval_and_stale_version_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = WorkflowProjectStore(root / "projects.sqlite3")
            project = store.create("Controlled review", _plan(root))
            with self.assertRaisesRegex(ValueError, "unknown gates"):
                store.set_approvals(
                    project["project_id"],
                    {"not-a-gate": True},
                    expected_version=1,
                )
            with self.assertRaisesRegex(RuntimeError, "version conflict"):
                store.set_approvals(
                    project["project_id"],
                    {"review_forecast": True},
                    expected_version=99,
                )

    def test_api_create_reopen_approve_and_execute(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = WorkflowProjectStore(
                root / "projects.sqlite3",
                output_root=root / "outputs",
            )
            original = workflow_project_routes.DEFAULT_WORKFLOW_PROJECT_STORE
            workflow_project_routes.DEFAULT_WORKFLOW_PROJECT_STORE = store
            try:
                client = TestClient(create_app())
                response = client.post(
                    "/api/v2/workflow-projects",
                    json={"name": "API forecast", "plan": _plan(root)},
                )
                self.assertEqual(response.status_code, 200, response.text)
                project = response.json()
                listed = client.get("/api/v2/workflow-projects").json()
                self.assertEqual(listed["projects"][0]["project_id"], project["project_id"])
                first = client.post(
                    f"/api/v2/workflow-projects/{project['project_id']}/executions",
                    json={"expected_version": project["version"]},
                )
                self.assertEqual(first.status_code, 200, first.text)
                pending = first.json()
                approved = client.post(
                    f"/api/v2/workflow-projects/{project['project_id']}/approvals",
                    json={
                        "decisions": {"review_forecast": True},
                        "expected_version": pending["version"],
                    },
                )
                self.assertEqual(approved.status_code, 200, approved.text)
                finished = client.post(
                    f"/api/v2/workflow-projects/{project['project_id']}/executions",
                    json={"expected_version": approved.json()["version"]},
                )
                self.assertEqual(finished.status_code, 200, finished.text)
                self.assertEqual(finished.json()["status"], "completed")
            finally:
                workflow_project_routes.DEFAULT_WORKFLOW_PROJECT_STORE = original

    def test_project_contract_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = WorkflowProjectStore(root / "projects.sqlite3").create(
                "Schema project",
                _plan(root),
            )
            contract_root = files("fmr.contracts")
            names = (
                "finance-workflow-request.v1.schema.json",
                "finance-workflow-plan.v1.schema.json",
                "workflow-project.v1.schema.json",
            )
            documents = {
                name: json.loads(contract_root.joinpath(name).read_text(encoding="utf-8"))
                for name in names
            }
            registry = Registry().with_resources(
                (document["$id"], Resource.from_contents(document))
                for document in documents.values()
            )
            Draft202012Validator(
                documents["workflow-project.v1.schema.json"],
                registry=registry,
            ).validate(project)


if __name__ == "__main__":
    unittest.main()
