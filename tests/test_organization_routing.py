from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fmr.core import routing_policy
from fmr.core.receipts import validate_route_decision
from fmr.organization import OrganizationPolicy, route_organization_job
from fmr.provider_service import prepare_handoff
from tests.test_provider_router import _job


def _policy(**overrides: object) -> dict:
    value = {
        "contract_version": "organization-routing-policy.v1",
        "organization_id": "acme",
        "version": "1.0.0",
        "private_provider_directories": [],
        "private_vocabulary_directories": [],
        "allowed_providers": ["native-xlsx", "python-forecast"],
        "provider_precedence": ["native-xlsx", "python-forecast"],
        "approved_provider_versions": ["native-xlsx@1.0.0", "python-forecast@1.1.0"],
        "approved_package_versions": ["native-xlsx/generic-budget-forecast@1.1.0", "python-forecast/generic-budget-forecast@1.1.0"],
        "prohibited_execution_modes": ["remote", "handoff_only"],
        "approved_template_ids": ["acme-budget-v3"],
        "require_approved_template": False,
        "local_only": True,
        "audit_retention_days": 2555,
    }
    value.update(overrides)
    return value


class OrganizationRoutingTests(unittest.TestCase):
    def test_organization_precedence_and_approvals_are_deterministic(self) -> None:
        policy = OrganizationPolicy.from_mapping(_policy())
        job = _job(output_formats=["json"])
        decision = route_organization_job(job, policy, base_policy=routing_policy("default"))
        self.assertEqual(decision["selected"]["provider_id"], "native-xlsx")
        self.assertEqual(decision["routing_policy"]["organization_id"], "acme")
        self.assertEqual(decision["routing_policy"]["audit_retention_days"], 2555)
        self.assertEqual(validate_route_decision(decision, job=policy.normalize_job(job), registry=policy.registry()), ())
        self.assertEqual(route_organization_job(job, policy, base_policy=routing_policy("default")), decision)

    def test_unapproved_versions_and_templates_fail_closed(self) -> None:
        job = _job(output_formats=["json"], existing_model={"template_id": "unapproved"})
        policy = OrganizationPolicy.from_mapping(_policy(require_approved_template=True))
        decision = route_organization_job(job, policy, base_policy=routing_policy("default"))
        self.assertEqual(decision["status"], "no_route")
        reasons = {reason for candidate in decision["candidate_evaluations"] for reason in candidate["rejection_reasons"]}
        self.assertIn("organization_template_not_approved", reasons)
        version_policy = OrganizationPolicy.from_mapping(_policy(approved_package_versions=["native-xlsx/generic-budget-forecast@9.9.9"]))
        version_decision = route_organization_job(_job(), version_policy, base_policy=routing_policy("default"))
        self.assertEqual(version_decision["status"], "no_route")
        self.assertTrue(all("organization_package_version_not_approved" in item["rejection_reasons"] for item in version_decision["candidate_evaluations"]))

    def test_private_vocabulary_normalizes_before_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vocabulary = {
                "contract_version": "industry-vocabulary.v1", "vocabulary_id": "acme-vertical", "version": "1.0.0",
                "kind": "industry", "canonical_industry": "logistics", "aliases": ["Acme Freight"],
                "concepts": [{"concept_id": "loads", "label": "Loads", "aliases": ["Shipments"]}],
            }
            (root / "vocabulary.json").write_text(json.dumps(vocabulary), encoding="utf-8")
            policy = OrganizationPolicy.from_mapping(_policy(private_vocabulary_directories=[str(root)]))
            model_job = policy.normalize_job(_job(industry="Acme Freight"))
            self.assertEqual(model_job.industry, "logistics")

    def test_handoff_pins_effective_organization_policy(self) -> None:
        policy = OrganizationPolicy.from_mapping(_policy())
        handoff = prepare_handoff(_job(output_formats=["json"]), organization_policy=policy)
        self.assertEqual(handoff["route_decision"]["routing_policy"]["organization_id"], "acme")

    def test_policy_rejects_precedence_outside_allowlist(self) -> None:
        with self.assertRaisesRegex(ValueError, "only allowed providers"):
            OrganizationPolicy.from_mapping(_policy(provider_precedence=["reference-handoff"]))


if __name__ == "__main__":
    unittest.main()
