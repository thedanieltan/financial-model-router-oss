from __future__ import annotations

import json
import copy
import hashlib
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from fmr.core import FAMILIES, ModelJob, route_job
from fmr.data import validate_canonical_financial_data
from fmr.core.receipts import validate_execution_result, validate_provider_handoff, validate_route_decision
from fmr.execution import ExecutionOrchestrator, ExecutionRequest, SqliteExecutionLedger
from fmr.provider_service import prepare_handoff
from fmr.registry import ProviderCatalog, ProviderManifest, ProviderRegistry
from fmr.sdk import build_provider_bundle, initialize_provider_project, run_manifest_conformance, validate_provider_project
from fmr.vocabulary import VocabularyRegistry
from fmr.adapters.sources import validate_source_adapter_profile
from tests.test_provider_router import _canonical_file, _job


class ContractTests(unittest.TestCase):
    def test_contracts_are_packaged_and_owned_by_this_repository(self) -> None:
        root = files("fmr.contracts")
        for name in (
            "model-job.v2.schema.json",
            "canonical-financial-data.v2.schema.json",
            "model-family-definition.v1.schema.json",
            "provider-manifest.v1.schema.json",
            "model-package-manifest.v1.schema.json",
            "route-decision.v2.schema.json",
            "provider-handoff.v1.schema.json",
            "provider-conformance-result.v1.schema.json",
            "provider-sdk-validation-result.v1.schema.json",
            "provider-sdk-package-result.v1.schema.json",
            "provider-registry.v1.schema.json",
            "provider-registry-audit.v1.schema.json",
            "provider-registry-reconciliation.v1.schema.json",
            "industry-vocabulary.v1.schema.json",
            "source-adapter-profile.v1.schema.json",
            "organization-routing-policy.v1.schema.json",
            "release-qualification.v1.schema.json",
            "deployment-acceptance-evidence.v1.schema.json",
            "model-acceptance-corpus.v1.schema.json",
            "model-acceptance-result.v1.schema.json",
            "execution-request.v1.schema.json",
            "execution-result.v1.schema.json",
            "execution-operations-status.v1.schema.json",
            "execution-ledger-backup.v1.schema.json",
            "execution-recovery-result.v1.schema.json",
            "artifact-retention-result.v1.schema.json",
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
            "workbook-coordinate-rule-registry.v1.schema.json",
            "workbook-coordinate-plan-request.v1.schema.json",
            "workbook-coordinate-plan.v1.schema.json",
            "workbook-content-spec-registry.v1.schema.json",
            "workbook-content-plan-request.v1.schema.json",
            "workbook-content-plan.v1.schema.json",
            "workbook-formula-spec-registry.v1.schema.json",
            "workbook-style-spec-registry.v1.schema.json",
            "workbook-realization-plan-request.v1.schema.json",
            "workbook-realization-plan.v1.schema.json",
            "workbook-write-context.v1.schema.json",
            "workbook-write-plan-request.v1.schema.json",
            "workbook-write-plan.v1.schema.json",
            "workbook-execution-request.v1.schema.json",
            "workbook-execution-result.v1.schema.json",
            "workbook-execution-receipt.v1.schema.json",
            "workbook-input-set-csv-request.v1.schema.json",
            "workbook-input-set.v1.schema.json",
            "workbook-input-population-request.v1.schema.json",
            "workbook-input-population-result.v1.schema.json",
            "workbook-input-population-receipt.v1.schema.json",
            "workbook-calculation-request.v1.schema.json",
            "workbook-calculation-result.v1.schema.json",
            "external-calculation-acceptance-request.v1.schema.json",
            "workbook-calculation-acceptance.v1.schema.json",
            "financial-concept-registry.v1.schema.json",
            "financial-data-package.v1.schema.json",
            "financial-data-mapping-profile.v1.schema.json",
            "financial-data-mapping-result.v1.schema.json",
            "financial-data-binding-profile.v1.schema.json",
            "workbook-input-binding-plan.v1.schema.json",
        ):
            schema = json.loads(root.joinpath(name).read_text(encoding="utf-8"))
            self.assertTrue(
                schema["$id"].startswith(
                    "https://github.com/thedanieltan/financial-model-router-oss/"
                )
            )

    def test_router_contract_schemas_accept_generated_lifecycle(self) -> None:
        validators = _validators()
        fixture_root = files("fmr.fixtures").joinpath("contracts")
        valid_job = json.loads(fixture_root.joinpath("valid-model-job.v2.json").read_text(encoding="utf-8"))
        validators["model-job.v2.schema.json"].validate(valid_job)
        ModelJob.from_mapping(valid_job)
        for manifest in ProviderRegistry.builtins().providers():
            validators["provider-manifest.v1.schema.json"].validate(manifest.to_dict())
            ProviderManifest.from_mapping(manifest.to_dict())
            validators["provider-conformance-result.v1.schema.json"].validate(run_manifest_conformance(manifest.to_dict()))
            for package in manifest.packages:
                validators["model-package-manifest.v1.schema.json"].validate(package.to_dict())
        for family in FAMILIES:
            validators["model-family-definition.v1.schema.json"].validate(family.to_dict())
        for vocabulary in VocabularyRegistry.builtins().vocabularies:
            validators["industry-vocabulary.v1.schema.json"].validate(vocabulary.to_dict())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = _job(_canonical_file(root), output_formats=["json"])
            canonical = json.loads(Path(job["input_references"]["canonical_financial_data"]["path"]).read_text())
            validators["canonical-financial-data.v2.schema.json"].validate(canonical)
            self.assertEqual(validate_canonical_financial_data(canonical), ())
            decision = route_job(job)
            handoff = prepare_handoff(job)
            request = {
                "contract_version": "execution-request.v1", "handoff": handoff, "idempotency_key": "schema",
                "execution_mode": handoff["execution_configuration"]["mode"], "timeout_seconds": 30,
                "secret_references": [], "output_policy": {"mode": "managed", "overwrite": False, "publish": False},
            }
            result = ExecutionOrchestrator(ledger=SqliteExecutionLedger(root / "ledger.sqlite3"), managed_output_root=root / "outputs").execute_request(request)
            ledger = SqliteExecutionLedger(root / "ledger.sqlite3")
            operations_status = ledger.operational_status()
            backup = ledger.backup(root / "ledger-backup.sqlite3")
            recovery = {"contract_version": "execution-recovery-result.v1", "recovered_count": 0}
            retention = {"contract_version": "artifact-retention-result.v1", "dry_run": True, "candidate_count": 0, "pruned_count": 0, "selected": []}
            provider_project = root / "provider-project"
            initialize_provider_project(provider_project, "schema-provider")
            sdk_validation = validate_provider_project(provider_project)
            sdk_package = build_provider_bundle(provider_project, root / "provider-dist")
            registry_manifest = ProviderRegistry.builtins().providers()[0].to_dict()
            registry_conformance = run_manifest_conformance(registry_manifest)
            registry_bundle = root / "registry-provider.zip"
            registry_bundle.write_bytes(b"registry provider")
            registry_receipt = {
                "contract_version": "provider-sdk-package-result.v1", "provider_id": registry_manifest["provider_id"],
                "path": str(registry_bundle), "sha256": hashlib.sha256(registry_bundle.read_bytes()).hexdigest(),
                "size_bytes": registry_bundle.stat().st_size, "member_count": 1,
            }
            catalog = ProviderCatalog(root / "provider-registry.json")
            catalog.submit(registry_manifest, registry_conformance, registry_receipt, available=False)
            registry_snapshot = catalog.snapshot()
            registry_audit = catalog.audit()
            registry_reconciliation = catalog.reconcile()
            for schema_name, payload in (
                ("model-job.v2.schema.json", ModelJob.from_mapping(job).to_dict()),
                ("route-decision.v2.schema.json", decision),
                ("provider-handoff.v1.schema.json", handoff),
                ("execution-request.v1.schema.json", request),
                ("execution-result.v1.schema.json", result),
                ("execution-operations-status.v1.schema.json", operations_status),
                ("execution-ledger-backup.v1.schema.json", backup),
                ("execution-recovery-result.v1.schema.json", recovery),
                ("artifact-retention-result.v1.schema.json", retention),
                ("provider-sdk-validation-result.v1.schema.json", sdk_validation),
                ("provider-sdk-package-result.v1.schema.json", sdk_package),
                ("provider-registry.v1.schema.json", registry_snapshot),
                ("provider-registry-audit.v1.schema.json", registry_audit),
                ("provider-registry-reconciliation.v1.schema.json", registry_reconciliation),
            ):
                validators[schema_name].validate(payload)
            self.assertEqual(validate_route_decision(decision, job=job), ())
            self.assertEqual(validate_provider_handoff(handoff), ())
            self.assertEqual(validate_execution_result(result, handoff=handoff), ())

    def test_invalid_fixture_corpus_and_python_validation_agree(self) -> None:
        validators = _validators()
        fixture_root = files("fmr.fixtures").joinpath("contracts")
        invalid_job = json.loads(fixture_root.joinpath("invalid-model-job-extra-field.v2.json").read_text(encoding="utf-8"))
        self.assertFalse(validators["model-job.v2.schema.json"].is_valid(invalid_job))
        with self.assertRaises(ValueError):
            ModelJob.from_mapping(invalid_job)
        invalid_manifest = json.loads(fixture_root.joinpath("invalid-provider-manifest.v1.json").read_text(encoding="utf-8"))
        self.assertFalse(validators["provider-manifest.v1.schema.json"].is_valid(invalid_manifest))
        with self.assertRaises(ValueError):
            ProviderManifest.from_mapping(invalid_manifest)
        handoff = prepare_handoff({
            "contract_version": "model-job.v2", "objective": "Prepare external DCF handoff",
            "model_family": "operating_company_dcf", "requested_deliverables": ["external_provider_handoff"],
            "available_data": [], "available_assumptions": [], "input_references": {}, "output_formats": ["json"]
        })
        bad_handoff = copy.deepcopy(handoff)
        bad_handoff["unexpected"] = True
        self.assertFalse(validators["provider-handoff.v1.schema.json"].is_valid(bad_handoff))
        self.assertTrue(validate_provider_handoff(bad_handoff))
        bad_route = copy.deepcopy(handoff["route_decision"])
        bad_route["unexpected"] = True
        self.assertFalse(validators["route-decision.v2.schema.json"].is_valid(bad_route))
        self.assertTrue(validate_route_decision(bad_route, job=handoff["job"]))
        bad_request = {"contract_version": "execution-request.v1", "handoff": handoff, "idempotency_key": "x", "execution_mode": "handoff_only", "timeout_seconds": 30, "secret_references": [], "output_policy": {"mode": "managed", "overwrite": False, "publish": False}, "ignored": True}
        self.assertFalse(validators["execution-request.v1.schema.json"].is_valid(bad_request))
        with self.assertRaises(ValueError):
            ExecutionRequest.from_mapping(bad_request)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = ExecutionOrchestrator(ledger=SqliteExecutionLedger(root / "ledger.sqlite3"), managed_output_root=root / "outputs").execute_request({key: value for key, value in bad_request.items() if key != "ignored"})
            bad_result = copy.deepcopy(result)
            bad_result["output_artifact_references"][0]["kind"] = "forged_output"
            self.assertFalse(validators["execution-result.v1.schema.json"].is_valid({**bad_result, "unexpected": True}))
            self.assertTrue(validate_execution_result(bad_result, handoff=handoff))

    def test_source_profile_schema_and_python_validation_agree(self) -> None:
        validators = _validators()
        profile = {
            "contract_version": "source-adapter-profile.v1",
            "profile_id": "generic-drivers",
            "profile_version": "1.0.0",
            "source_system": "generic",
            "source_type": "operational_driver",
            "format": "csv",
            "sheet_name": None,
            "columns": {"period": "Period", "driver_id": "Driver", "value": "Value"},
        }
        validators["source-adapter-profile.v1.schema.json"].validate(profile)
        self.assertEqual(validate_source_adapter_profile(profile), ())
        invalid = copy.deepcopy(profile)
        invalid["columns"]["unexpected"] = "Unexpected"
        self.assertFalse(validators["source-adapter-profile.v1.schema.json"].is_valid(invalid))
        self.assertTrue(validate_source_adapter_profile(invalid))


def _validators() -> dict[str, Draft202012Validator]:
    root = files("fmr.contracts")
    names = ("artifact-retention-result.v1.schema.json", "canonical-financial-data.v2.schema.json", "execution-ledger-backup.v1.schema.json", "execution-operations-status.v1.schema.json", "execution-recovery-result.v1.schema.json", "industry-vocabulary.v1.schema.json", "source-adapter-profile.v1.schema.json", "model-family-definition.v1.schema.json", "model-job.v2.schema.json", "model-package-manifest.v1.schema.json", "provider-conformance-result.v1.schema.json", "provider-manifest.v1.schema.json", "provider-sdk-validation-result.v1.schema.json", "provider-sdk-package-result.v1.schema.json", "provider-registry.v1.schema.json", "provider-registry-audit.v1.schema.json", "provider-registry-reconciliation.v1.schema.json", "route-decision.v2.schema.json", "provider-handoff.v1.schema.json", "execution-request.v1.schema.json", "execution-result.v1.schema.json")
    documents = {name: json.loads(root.joinpath(name).read_text(encoding="utf-8")) for name in names}
    registry = Registry().with_resources((document["$id"], Resource.from_contents(document)) for document in documents.values())
    return {name: Draft202012Validator(document, registry=registry) for name, document in documents.items()}


if __name__ == "__main__":
    unittest.main()
