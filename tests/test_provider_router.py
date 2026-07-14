from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from fmr.adapters.sources import statement_mapping_to_canonical_data
from fmr.core import FAMILIES, ModelJob, route_job, routing_policy
from fmr.core.handoffs import digest
from fmr.core.receipts import validate_execution_result, validate_provider_handoff, validate_route_decision
from fmr.execution import ExecutionOrchestrator, SqliteExecutionLedger, _execute_with_timeout
from fmr.financial_data import build_mapping_profile, import_statement_csv, map_financial_data
from fmr.provider_service import prepare_handoff
from fmr.providers.native_xlsx import validate_budget_workbook
from fmr.registry import ProviderManifest, ProviderRegistry
from fmr.sdk import run_manifest_conformance, run_provider_conformance
from tests.financial_data_case import statement_csv_bytes
from tests.test_executor import execution_case


ASSUMPTION_NAMES = ["forecast_horizon", "operating_cost_growth_rate", "revenue_growth_rate", "scenario", "scenario_adjustments"]


def _job(reference: dict | None = None, **overrides: object) -> dict:
    value = {
        "contract_version": "model-job.v2",
        "objective": "Prepare an operating budget and forecast",
        "requested_deliverables": ["budget_forecast"],
        "industry": "logistics",
        "available_data": ["income_statement_history", "operating_cost_drivers", "revenue_drivers"],
        "available_assumptions": ASSUMPTION_NAMES,
        "input_references": {"canonical_financial_data": reference or {"uri": "memory://canonical", "sha256": "a" * 64, "contract_version": "canonical-financial-data.v2"}},
        "output_formats": ["xlsx"],
        "constraints": {"open_source_only": True},
    }
    value.update(overrides)
    return value


def _reference_job(**overrides: object) -> dict:
    value = {
        "contract_version": "model-job.v2", "objective": "Prepare an external DCF provider handoff",
        "model_family": "operating_company_dcf", "requested_deliverables": ["external_provider_handoff"],
        "available_data": [], "available_assumptions": [], "input_references": {}, "output_formats": ["json"],
        "preferred_execution_mode": "handoff_only",
    }
    value.update(overrides)
    return value


def _canonical_file(root: Path) -> dict:
    source = root / "canonical.json"
    source.write_text(json.dumps({
        "contract_version": "canonical-financial-data.v2",
        "entity": {"entity_id": "synthetic-co", "currency": "USD"},
        "periods": ["2025", "2026"],
        "financial_statements": {"income_statement": {"revenue": ["100.0", "110.0"], "operating_costs": ["60.0", "63.0"]}},
        "trial_balance": [], "account_balances": [], "debt_schedules": [], "capital_expenditure": [], "working_capital": [],
        "operational_drivers": {"units": ["100", "105"]},
        "assumptions": {
            "forecast_horizon": 2, "revenue_growth_rate": "0.10", "operating_cost_growth_rate": "0.05", "scenario": "upside",
            "scenario_adjustments": {"upside": {"revenue_growth_delta": "0.02", "operating_cost_growth_delta": "-0.01"}},
        },
        "provenance": [{"source": "synthetic-test"}],
    }), encoding="utf-8")
    return {"path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "contract_version": "canonical-financial-data.v2"}


def _orchestrator(root: Path, registry: ProviderRegistry | None = None) -> ExecutionOrchestrator:
    return ExecutionOrchestrator(registry=registry, ledger=SqliteExecutionLedger(root / "ledger.sqlite3"), managed_output_root=root / "managed")


class JobAndFamilyTests(unittest.TestCase):
    def test_explicit_family_is_provider_neutral(self) -> None:
        decision = route_job(ModelJob.from_mapping(_job(model_family="budget_forecast")))
        self.assertEqual(decision["family_classification"]["selected_family"], "budget_forecast")
        self.assertEqual(validate_route_decision(decision, job=_job(model_family="budget_forecast")), ())

    def test_ambiguous_and_unsupported_families_are_structured(self) -> None:
        ambiguous = _job(objective="Compare a budget and DCF", requested_deliverables=["analysis"])
        self.assertEqual(route_job(ambiguous)["status"], "ambiguous_family")
        unsupported = _job(objective="Price a weather derivative", requested_deliverables=["weather_derivative"])
        self.assertEqual(route_job(unsupported)["status"], "unsupported_family")

    def test_family_definitions_contain_no_provider_details(self) -> None:
        forbidden = ("coordinate", "openpyxl", "sheet layout", "excel formula")
        for family in FAMILIES:
            rendered = json.dumps(family.to_dict()).lower()
            self.assertFalse(any(token in rendered for token in forbidden), family.family_id)


class RegistryAndRoutingTests(unittest.TestCase):
    def test_manifest_discovery_is_dynamic_and_code_free(self) -> None:
        registry = ProviderRegistry.builtins()
        self.assertEqual([item.provider_id for item in registry.providers()], ["native-xlsx", "python-forecast", "reference-handoff"])
        self.assertEqual(len(registry.packages("budget_forecast")), 3)
        for provider in registry.providers():
            self.assertEqual(run_manifest_conformance(provider.to_dict())["status"], "passed")
        completed = subprocess.run([sys.executable, "-c", "import sys; from fmr.registry import ProviderRegistry; ProviderRegistry.builtins(); assert 'fmr.providers.native_xlsx.provider' not in sys.modules; assert 'fmr.providers.python_forecast.plugin' not in sys.modules"], check=False, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_configured_manifest_directory_registers_without_router_change(self) -> None:
        manifest = ProviderRegistry.builtins().providers()[1].to_dict()
        manifest["packages"] = manifest["packages"][:1]
        manifest["provider_id"] = "third-party"
        manifest["executor_entry_point"] = "missing-executor"
        manifest["packages"][0]["package_id"] = "third-party/budget"
        manifest["packages"][0]["adapter_entry_point"] = "missing-adapter"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "provider"
            path.mkdir()
            (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            registry = ProviderRegistry.discover(manifest_directories=[temporary], disabled_providers=("native-xlsx", "python-forecast", "reference-handoff"))
            decision = route_job(_job(output_formats=["json"]), registry=registry)
            self.assertEqual(decision["status"], "no_route")
            self.assertIn("provider_adapter_unavailable", decision["missing_requirements"])
            self.assertIn("provider_executor_unavailable", decision["missing_requirements"])

    def test_two_real_implementations_compete_under_policy(self) -> None:
        job = _job(output_formats=["json"])
        json_first = route_job(job, policy=routing_policy("json-first"))
        spreadsheet_first = route_job(job, policy=routing_policy("spreadsheet-first"))
        self.assertEqual(json_first["selected"]["provider_id"], "python-forecast")
        self.assertEqual(spreadsheet_first["selected"]["provider_id"], "native-xlsx")
        self.assertEqual(route_job(job, policy=routing_policy("json-first")), json_first)

    def test_reference_handoff_cannot_compete_for_xlsx_or_model_deliverables(self) -> None:
        budget = route_job(_job())
        self.assertEqual(budget["selected"]["provider_id"], "native-xlsx")
        self.assertNotIn("reference-handoff", {item["provider_id"] for item in budget["candidate_evaluations"]})
        dcf_model = route_job(_reference_job(requested_deliverables=["enterprise_value"]))
        self.assertEqual(dcf_model["status"], "no_route")
        handoff = route_job(_reference_job())
        self.assertEqual(handoff["selected"]["provider_id"], "reference-handoff")

    def test_no_route_and_hard_rejections_are_explicit(self) -> None:
        decision = route_job(_job(available_data=[], available_assumptions=[]))
        self.assertEqual(decision["status"], "no_route")
        self.assertIn("missing_data:income_statement_history", decision["missing_requirements"])
        constrained = route_job(_job(privacy_constraints=["customer_managed_keys"], licensing_constraints=["MIT"]))
        reasons = {reason for item in constrained["rejected_candidates"] for reason in item["reasons"]}
        self.assertIn("license_not_allowed", reasons)


class IntegrityAndExecutionTests(unittest.TestCase):
    def test_existing_workbook_runtime_remains_compatible(self) -> None:
        from fmr.providers.native_xlsx.legacy import execute_workbook_write_plan_bytes
        source, write_plan = execution_case()
        self.assertEqual(execute_workbook_write_plan_bytes(source, filename="source.xlsx", output_filename="output.xlsx", write_plan=write_plan).receipt["status"], "completed")

    def test_statement_source_adapter_does_not_invent_values(self) -> None:
        package = import_statement_csv(statement_csv_bytes(include_unmapped=False), source_name="synthetic.csv")
        profile = build_mapping_profile([{"account_code": "6000", "account_name": None, "concept_id": "operating_costs"}])
        mapping = map_financial_data(package, profile=profile)
        canonical = statement_mapping_to_canonical_data(package, mapping, assumptions={"forecast_horizon": 2})
        self.assertEqual(canonical["trial_balance"], [])
        self.assertEqual(canonical["assumptions"], {"forecast_horizon": 2})

    def test_mutated_or_fabricated_handoff_is_refused(self) -> None:
        handoff = prepare_handoff(_reference_job())
        self.assertEqual(validate_provider_handoff(handoff), ())
        mutated = copy.deepcopy(handoff)
        mutated["provider_payload"]["external_request"]["objective"] = "forged"
        self.assertIn("handoff_sha256 does not match complete canonical payload", validate_provider_handoff(mutated))
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "invalid provider handoff"):
                _orchestrator(Path(temporary)).execute(mutated, idempotency_key="forged")

    def test_handoff_only_produces_only_the_promised_json_handoff(self) -> None:
        handoff = prepare_handoff(_reference_job())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            orchestrator = _orchestrator(root)
            result = orchestrator.execute(handoff, idempotency_key="handoff", output_dir=root / "outputs")
            self.assertEqual(result["state"], "completed")
            self.assertEqual([item["kind"] for item in result["output_artifact_references"]], ["external_provider_handoff"])
            self.assertEqual(validate_execution_result(result, handoff=handoff), ())

    def test_native_xlsx_is_a_driver_based_scenario_forecast(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = prepare_handoff(_job(_canonical_file(root)), policy_name="spreadsheet-first")
            result = _orchestrator(root).execute(handoff, idempotency_key="native", output_dir=root / "outputs")
            self.assertEqual(result["state"], "completed")
            artifacts = {item["kind"]: item for item in result["output_artifact_references"]}
            self.assertEqual(validate_budget_workbook(artifacts["budget_forecast_workbook"]["path"])["status"], "passed")
            forecast = json.loads(Path(artifacts["budget_forecast"]["path"]).read_text())
            self.assertEqual(forecast["actual_periods"], ["2025", "2026"])
            self.assertEqual(forecast["forecast_periods"], ["2027", "2028"])
            self.assertEqual(forecast["scenario"], "upside")
            self.assertEqual(forecast["forecast"][0]["revenue"], "123.20")
            self.assertEqual(validate_execution_result(result, handoff=handoff), ())

    def test_python_forecast_is_second_executable_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = _job(_canonical_file(root), output_formats=["json"])
            handoff = prepare_handoff(job, policy_name="json-first")
            self.assertEqual(handoff["provider"]["provider_id"], "python-forecast")
            result = _orchestrator(root).execute(handoff, idempotency_key="python", output_dir=root / "outputs")
            self.assertEqual(result["state"], "completed")
            self.assertEqual(result["output_artifact_references"][0]["kind"], "budget_forecast")

    def test_durable_idempotency_revalidates_cached_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = prepare_handoff(_reference_job())
            first = _orchestrator(root).execute(handoff, idempotency_key="same", output_dir=root / "outputs")
            second = _orchestrator(root).execute(handoff, idempotency_key="same", output_dir=root / "outputs")
            self.assertEqual(first, second)
            Path(first["output_artifact_references"][0]["path"]).unlink()
            with self.assertRaisesRegex(RuntimeError, "no longer valid"):
                _orchestrator(root).execute(handoff, idempotency_key="same", output_dir=root / "outputs")

    def test_execution_mode_and_unused_secrets_are_rejected(self) -> None:
        handoff = prepare_handoff(_reference_job())
        with tempfile.TemporaryDirectory() as temporary:
            orchestrator = _orchestrator(Path(temporary))
            base = {"contract_version": "execution-request.v1", "handoff": handoff, "idempotency_key": "x", "execution_mode": "local", "timeout_seconds": 30, "secret_references": [], "output_policy": {"mode": "managed", "overwrite": False, "publish": False}}
            with self.assertRaisesRegex(ValueError, "execution_mode"):
                orchestrator.execute_request(base)
            base["execution_mode"] = "handoff_only"
            base["secret_references"] = ["UNDECLARED"]
            with self.assertRaisesRegex(ValueError, "secret references"):
                orchestrator.execute_request(base)

    def test_invalid_input_and_provider_timeout_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = _canonical_file(root)
            handoff = prepare_handoff(_job(reference), policy_name="spreadsheet-first")
            Path(reference["path"]).write_text("{}", encoding="utf-8")
            result = _orchestrator(root).execute(handoff, idempotency_key="bad-input", output_dir=root / "outputs")
            self.assertEqual(result["state"], "failed")
            self.assertEqual(result["error_category"], "invalid_input")
            self.assertFalse(result["retry_eligible"])
            partial = root / "partial"
            partial.mkdir()
            (partial / "partial.tmp").write_text("partial", encoding="utf-8")
            with mock.patch("fmr.execution.subprocess.run", side_effect=subprocess.TimeoutExpired(["provider"], 1)):
                with self.assertRaisesRegex(RuntimeError, "timed out"):
                    _execute_with_timeout("native-xlsx", handoff, partial, {}, 1)
            self.assertFalse(partial.exists())

    def test_executable_provider_conformance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = _canonical_file(root)
            jobs = {"native-xlsx": _job(reference), "python-forecast": _job(reference, output_formats=["json"]), "reference-handoff": _reference_job()}
            for manifest in ProviderRegistry.builtins().providers():
                result = run_provider_conformance(manifest.to_dict(), jobs[manifest.provider_id])
                self.assertEqual(result["status"], "passed", result)


if __name__ == "__main__":
    unittest.main()
