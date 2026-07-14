from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import subprocess
import sys
from pathlib import Path

from fmr.core import FAMILIES, LOCAL_ONLY_POLICY, ModelJob, route_job
from fmr.adapters.sources import statement_mapping_to_canonical_data
from fmr.core.handoffs import digest
from fmr.core.receipts import validate_execution_result
from fmr.execution import ExecutionOrchestrator
from fmr.provider_service import prepare_handoff
from fmr.providers.native_xlsx import validate_budget_workbook
from fmr.registry import ProviderManifest, ProviderRegistry
from fmr.sdk import run_provider_conformance
from fmr.financial_data import build_mapping_profile, import_statement_csv, map_financial_data
from tests.financial_data_case import statement_csv_bytes
from tests.test_executor import execution_case


def _job(reference: dict | None = None, **overrides: object) -> dict:
    value = {
        "contract_version": "model-job.v2",
        "objective": "Prepare an operating budget and forecast",
        "requested_deliverables": ["budget_forecast"],
        "industry": "logistics",
        "available_data": ["income_statement_history", "operating_cost_drivers", "revenue_drivers"],
        "available_assumptions": ["forecast_horizon"],
        "input_references": {"canonical_financial_data": reference or {"uri": "memory://canonical", "sha256": "a" * 64, "contract_version": "canonical-financial-data.v2"}},
        "output_formats": ["xlsx"],
        "constraints": {"open_source_only": True},
    }
    value.update(overrides)
    return value


class JobAndFamilyTests(unittest.TestCase):
    def test_explicit_family_is_provider_neutral(self) -> None:
        job = ModelJob.from_mapping(_job(model_family="budget_forecast"))
        decision = route_job(job)
        self.assertEqual(decision["family_classification"]["selected_family"], "budget_forecast")

    def test_ambiguous_and_unsupported_families_are_structured(self) -> None:
        ambiguous = _job(objective="Compare a budget and DCF", requested_deliverables=["analysis"])
        self.assertEqual(route_job(ambiguous)["status"], "ambiguous_family")
        unsupported = _job(objective="Price a weather derivative", requested_deliverables=["weather_derivative"])
        self.assertEqual(route_job(unsupported)["status"], "unsupported_family")

    def test_family_definitions_contain_no_xlsx_implementation_details(self) -> None:
        forbidden = ("coordinate", "openpyxl", "sheet layout", "excel formula")
        for family in FAMILIES:
            rendered = json.dumps(family.to_dict()).lower()
            self.assertFalse(any(token in rendered for token in forbidden), family.family_id)


class RegistryAndRoutingTests(unittest.TestCase):
    def test_two_providers_are_discovered_without_execution_imports(self) -> None:
        registry = ProviderRegistry.builtins()
        self.assertEqual([item.provider_id for item in registry.providers()], ["native-xlsx", "reference-handoff"])
        self.assertEqual(len(registry.packages("budget_forecast")), 2)
        for provider in registry.providers():
            self.assertEqual(run_provider_conformance(provider.to_dict())["status"], "passed")
        completed = subprocess.run(
            [sys.executable, "-c", "import sys; from fmr.registry import ProviderRegistry; ProviderRegistry.builtins(); assert 'fmr.providers.native_xlsx.provider' not in sys.modules"],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_invalid_manifest_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "contract"):
            ProviderManifest.from_mapping({})

    def test_manifest_registers_without_router_code_change(self) -> None:
        manifest = ProviderManifest.from_mapping({
            "contract_version": "provider-manifest.v1", "provider_id": "third-party", "version": "1.0.0",
            "execution_mode": "handoff_only", "network_required": False, "license": "Apache-2.0", "open_source": True,
            "privacy_behavior": ["value_free_receipts"], "runtime_dependencies": [], "determinism_level": "deterministic_handoff",
            "validation_capabilities": ["handoff_contract"], "limitations": [],
            "packages": [{"contract_version": "model-package-manifest.v1", "package_id": "third-party/budget", "version": "1.0.0",
                "model_family": "budget_forecast", "industries": ["*"], "deliverables": ["budget_forecast"],
                "required_data": ["income_statement_history", "operating_cost_drivers", "revenue_drivers"],
                "required_assumptions": ["forecast_horizon"], "accepted_inputs": ["canonical-financial-data.v2"],
                "output_artifacts": ["budget_forecast_workbook"], "output_formats": ["xlsx"],
                "validation_checks": ["handoff_contract"], "execution_capabilities": ["prepare_handoff"], "adapter_id": "third-party/budget.v1"}],
        })
        registry = ProviderRegistry([manifest], runtime_availability={"third-party": True})
        decision = route_job(_job(), registry=registry)
        self.assertEqual(decision["status"], "no_route")
        self.assertIn("provider_adapter_unavailable", decision["missing_requirements"])

    def test_policy_changes_the_deterministic_route(self) -> None:
        default = route_job(_job())
        local = route_job(_job(), policy=LOCAL_ONLY_POLICY)
        self.assertEqual(default["selected"]["provider_id"], "reference-handoff")
        self.assertEqual(local["selected"]["provider_id"], "native-xlsx")
        self.assertEqual(route_job(_job()), default)

    def test_no_route_is_first_class_and_rejections_are_explained(self) -> None:
        missing = _job(available_data=[], available_assumptions=[])
        decision = route_job(missing)
        self.assertEqual(decision["status"], "no_route")
        self.assertIn("missing_data:income_statement_history", decision["missing_requirements"])
        local_registry = ProviderRegistry.builtins(disabled_providers=("native-xlsx",))
        rejected = route_job(_job(), policy=LOCAL_ONLY_POLICY, registry=local_registry)
        self.assertEqual(rejected["status"], "no_route")
        self.assertIn("local_only_requires_local_provider", rejected["rejected_candidates"][0]["reasons"])
        unavailable = ProviderRegistry.builtins(runtime_availability={"native-xlsx": False})
        runtime_decision = route_job(_job(), policy=LOCAL_ONLY_POLICY, registry=unavailable)
        self.assertEqual(runtime_decision["status"], "no_route")
        self.assertIn("runtime_unavailable", runtime_decision["rejected_candidates"][0]["reasons"])

    def test_non_xlsx_route_remains_valid_when_native_provider_is_disabled(self) -> None:
        registry = ProviderRegistry.builtins(disabled_providers=("native-xlsx",))
        job = _job(
            objective="Value an operating company using DCF",
            model_family="operating_company_dcf",
            requested_deliverables=["operating_forecast", "enterprise_value", "equity_value"],
            available_data=["capital_expenditure", "cash_flow_history", "income_statement_history", "net_debt", "revenue_drivers", "working_capital"],
            available_assumptions=["discount_rate", "forecast_horizon", "tax_rate", "terminal_value_assumption"],
            output_formats=["json"],
        )
        decision = route_job(job, registry=registry)
        self.assertEqual(decision["status"], "selected")
        self.assertEqual(decision["selected"]["package_id"], "reference-handoff/operating-company-dcf")

    def test_privacy_and_license_constraints_are_hard_rejections(self) -> None:
        decision = route_job(_job(privacy_constraints=["customer_managed_keys"], licensing_constraints=["MIT"]))
        self.assertEqual(decision["status"], "no_route")
        reasons = {reason for item in decision["rejected_candidates"] for reason in item["reasons"]}
        self.assertIn("license_not_allowed", reasons)
        self.assertTrue(any(reason.startswith("privacy_constraint_not_met:") for reason in reasons))


class HandoffAndExecutionTests(unittest.TestCase):
    def test_existing_workbook_runtime_is_available_through_native_provider(self) -> None:
        from fmr.providers.native_xlsx.legacy import execute_workbook_write_plan_bytes
        source, write_plan = execution_case()
        result = execute_workbook_write_plan_bytes(source, filename="source.xlsx", output_filename="output.xlsx", write_plan=write_plan)
        self.assertEqual(result.receipt["status"], "completed")

    def test_statement_source_adapter_builds_canonical_v2_without_invention(self) -> None:
        package = import_statement_csv(statement_csv_bytes(include_unmapped=False), source_name="synthetic.csv")
        profile = build_mapping_profile([{"account_code": "6000", "account_name": None, "concept_id": "operating_costs"}])
        mapping = map_financial_data(package, profile=profile)
        canonical = statement_mapping_to_canonical_data(package, mapping, assumptions={"forecast_horizon": 2})
        self.assertEqual(canonical["contract_version"], "canonical-financial-data.v2")
        self.assertEqual(canonical["trial_balance"], [])
        self.assertEqual(canonical["assumptions"], {"forecast_horizon": 2})

    def test_handoff_only_execution_is_idempotent_and_chained(self) -> None:
        handoff = prepare_handoff(_job())
        self.assertEqual(handoff["provider"]["provider_id"], "reference-handoff")
        self.assertEqual(handoff["status"], "ready")
        self.assertEqual(handoff["job_reference"]["sha256"], digest(ModelJob.from_mapping(_job()).to_dict()))
        orchestrator = ExecutionOrchestrator()
        first = orchestrator.execute(handoff, idempotency_key="same-key")
        second = orchestrator.execute(handoff, idempotency_key="same-key")
        self.assertEqual(first, second)
        self.assertEqual(first["state"], "completed")
        self.assertEqual(validate_execution_result(first), ())

    def test_handoff_remains_blocked_while_requirements_are_missing(self) -> None:
        handoff = prepare_handoff(_job(available_data=[], available_assumptions=[]))
        self.assertEqual(handoff["status"], "blocked")
        self.assertTrue(handoff["unresolved_requirements"])
        result = ExecutionOrchestrator().execute(handoff, idempotency_key="blocked")
        self.assertEqual(result["state"], "blocked")

    def test_handoff_rejects_embedded_secrets(self) -> None:
        reference = {"uri": "memory://canonical", "sha256": "a" * 64, "contract_version": "canonical-financial-data.v2", "access_token": "must-not-be-here"}
        with self.assertRaisesRegex(ValueError, "Secrets|secrets"):
            prepare_handoff(_job(reference))

    def test_native_xlsx_route_produces_and_validates_workbook(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "canonical.json"
            source.write_text(json.dumps({
                "contract_version": "canonical-financial-data.v2",
                "entity": {"entity_id": "synthetic-co", "currency": "USD"},
                "periods": ["2026", "2027"],
                "financial_statements": {"income_statement": {"revenue": ["100.0", "115.0"], "operating_costs": ["60.0", "68.0"]}},
                "trial_balance": [], "account_balances": [], "debt_schedules": [],
                "capital_expenditure": [], "working_capital": [],
                "operational_drivers": {}, "assumptions": {"forecast_horizon": 2},
                "provenance": [{"source": "synthetic-test"}],
            }), encoding="utf-8")
            reference = {"path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "contract_version": "canonical-financial-data.v2"}
            handoff = prepare_handoff(_job(reference), policy_name="local-only")
            result = ExecutionOrchestrator().execute(handoff, idempotency_key="native-case", output_dir=root / "outputs")
            self.assertEqual(result["state"], "completed", result)
            artifact = result["output_artifact_references"][0]
            self.assertEqual(validate_budget_workbook(artifact["path"])["status"], "passed")
            self.assertEqual(validate_execution_result(result), ())


if __name__ == "__main__":
    unittest.main()
