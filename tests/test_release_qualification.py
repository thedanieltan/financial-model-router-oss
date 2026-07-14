from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from fmr.entrypoint import main
from fmr.qualification import DEPLOYMENT_GATES, qualify_local_release, validate_deployment_evidence


def _evidence(status: str = "passed") -> dict:
    return {
        "contract_version": "deployment-acceptance-evidence.v1",
        "environment_id": "synthetic-ci",
        "gates": {gate: {"status": status, "reference": f"evidence://{gate}"} for gate in DEPLOYMENT_GATES},
    }


class ReleaseQualificationTests(unittest.TestCase):
    def test_implementation_gates_pass_but_alpha_is_not_production(self) -> None:
        report = qualify_local_release()
        self.assertEqual(report["implementation_status"], "passed")
        self.assertEqual(report["production_status"], "not_accepted")
        self.assertIn("stable_release_version_not_declared", report["blockers"])
        self.assertTrue(all(item["status"] == "passed" for item in report["implementation_checks"]))
        self.assertTrue(all(item["status"] == "not_run" for item in report["deployment_gates"]))
        self.assertEqual(report, qualify_local_release())

    def test_complete_deployment_evidence_still_does_not_override_alpha_maturity(self) -> None:
        evidence = _evidence()
        self.assertEqual(validate_deployment_evidence(evidence), ())
        report = qualify_local_release(evidence)
        self.assertEqual(report["production_status"], "not_accepted")
        self.assertEqual(report["blockers"], ["stable_release_version_not_declared"])

    def test_invalid_or_failed_evidence_is_retained_as_blockers(self) -> None:
        evidence = _evidence()
        evidence["gates"]["security_review"] = {"status": "failed", "reference": "evidence://failed-review"}
        report = qualify_local_release(evidence)
        self.assertIn("security_review", report["blockers"])
        invalid = copy.deepcopy(evidence)
        del invalid["gates"]["resource_limits"]
        self.assertTrue(validate_deployment_evidence(invalid))
        invalid_report = qualify_local_release(invalid)
        self.assertTrue(any(item.startswith("invalid_deployment_evidence:") for item in invalid_report["blockers"]))

    def test_contract_schemas_accept_reports_and_evidence(self) -> None:
        root = Path(__file__).parents[1] / "fmr" / "contracts"
        report_schema = json.loads((root / "release-qualification.v1.schema.json").read_text())
        evidence_schema = json.loads((root / "deployment-acceptance-evidence.v1.schema.json").read_text())
        evidence = _evidence()
        Draft202012Validator(evidence_schema).validate(evidence)
        Draft202012Validator(report_schema).validate(qualify_local_release(evidence))

    def test_cli_separates_implementation_and_production_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "qualification.json"
            self.assertEqual(main(["qualify-release", "--output", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text())["implementation_status"], "passed")
            self.assertEqual(main(["qualify-release", "--require-production", "--output", str(output)]), 2)


if __name__ == "__main__":
    unittest.main()
