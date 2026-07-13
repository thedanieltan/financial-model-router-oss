from __future__ import annotations

import base64
import unittest

from fastapi.testclient import TestClient

from fmr.api.composed import create_app
from tests.financial_data_case import financial_data_case, statement_csv_bytes


class FinancialDataApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())

    def test_financial_data_endpoints_compile_governed_input_set(self) -> None:
        _, mapping_profile, _, binding_profile, _, execution = financial_data_case()
        imported = self.client.post(
            "/api/v1/financial-data/packages/from-csv",
            json={
                "contract_version": "financial-data-csv-request.v1",
                "source_name": "statements.csv",
                "csv_base64": base64.b64encode(statement_csv_bytes()).decode("ascii"),
            },
        )
        self.assertEqual(imported.status_code, 200)
        package = imported.json()

        profile_response = self.client.post(
            "/api/v1/financial-data/mapping-profiles",
            json={"name": "mapping", "rules": mapping_profile["rules"]},
        )
        self.assertEqual(profile_response.status_code, 200)
        mapping_profile_payload = profile_response.json()

        mapping_response = self.client.post(
            "/api/v1/financial-data/mappings",
            json={"package": package, "profile": mapping_profile_payload},
        )
        self.assertEqual(mapping_response.status_code, 200)
        mapping = mapping_response.json()

        binding_profile_response = self.client.post(
            "/api/v1/financial-data/binding-profiles",
            json={"name": "binding", "bindings": binding_profile["bindings"]},
        )
        self.assertEqual(binding_profile_response.status_code, 200)
        binding_profile_payload = binding_profile_response.json()

        binding_response = self.client.post(
            "/api/v1/financial-data/binding-plans",
            json={
                "package": package,
                "mapping_result": mapping,
                "binding_profile": binding_profile_payload,
                "write_plan": execution["write_plan"],
                "execution_receipt": execution["execution_receipt"],
            },
        )
        self.assertEqual(binding_response.status_code, 200)
        binding_plan = binding_response.json()
        self.assertTrue(binding_plan["ready_for_input_set"])

        input_set_response = self.client.post(
            "/api/v1/financial-data/input-sets",
            json={
                "binding_plan": binding_plan,
                "write_plan": execution["write_plan"],
                "execution_receipt": execution["execution_receipt"],
            },
        )
        self.assertEqual(input_set_response.status_code, 200)
        self.assertEqual(
            input_set_response.json()["contract_version"],
            "workbook-input-set.v1",
        )

    def test_concept_registry_and_validation_endpoints(self) -> None:
        response = self.client.get("/api/v1/financial-concepts")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["contract_version"],
            "financial-concept-registry.v1",
        )
        package, profile, mapping, binding_profile, binding_plan, execution = (
            financial_data_case()
        )
        package_validation = self.client.post(
            "/api/v1/financial-data/packages/validate",
            json={"package": package},
        )
        self.assertEqual(package_validation.json(), {"valid": True, "issues": []})
        mapping_validation = self.client.post(
            "/api/v1/financial-data/mappings/validate",
            json={
                "mapping_result": mapping,
                "package": package,
                "profile": profile,
            },
        )
        self.assertEqual(mapping_validation.json(), {"valid": True, "issues": []})
        binding_validation = self.client.post(
            "/api/v1/financial-data/binding-plans/validate",
            json={
                "binding_plan": binding_plan,
                "package": package,
                "mapping_result": mapping,
                "binding_profile": binding_profile,
                "write_plan": execution["write_plan"],
                "execution_receipt": execution["execution_receipt"],
            },
        )
        self.assertEqual(binding_validation.json(), {"valid": True, "issues": []})

    def test_invalid_base64_is_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/financial-data/packages/from-csv",
            json={
                "contract_version": "financial-data-csv-request.v1",
                "source_name": "statements.csv",
                "csv_base64": "invalid!",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_financial_data_browser_asset_is_served(self) -> None:
        response = self.client.get("/assets/financial_data.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("importFinancialData", response.text)
        self.assertIn("/api/v1/financial-data/binding-plans", response.text)


if __name__ == "__main__":
    unittest.main()
