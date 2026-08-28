from __future__ import annotations

import json
import unittest
from importlib.resources import files

from jsonschema import Draft202012Validator

from fmr.core import FAMILIES
from fmr.knowledge import AnalystWorkflowMethod, FamilyPlaybook, KnowledgeRegistry


class ModelKnowledgeTests(unittest.TestCase):
    def test_builtins_cover_registered_families_and_are_deterministic(self) -> None:
        first = KnowledgeRegistry.builtins()
        second = KnowledgeRegistry.builtins()
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(first.version, "1.1.0")
        self.assertEqual({item.family_id for item in first.playbooks}, {item.family_id for item in FAMILIES})
        self.assertEqual({item.family_id for item in first.methods}, {item.family_id for item in FAMILIES})
        self.assertTrue(all(item.review_state == "synthetic_reviewed" for item in first.playbooks))
        self.assertTrue(all(item.review_state == "reference_grounded" for item in first.methods))
        self.assertEqual(len(first.sources), 16)
        self.assertEqual(len(first.questions), 5)

    def test_bundled_knowledge_files_validate_against_json_schema(self) -> None:
        contracts = files("fmr.contracts")
        data = files("fmr.knowledge.data")
        source_schema = Draft202012Validator(json.loads(contracts.joinpath("knowledge-source-registry.v1.schema.json").read_text()))
        question_schema = Draft202012Validator(json.loads(contracts.joinpath("scope-question-set.v1.schema.json").read_text()))
        playbook_schema = Draft202012Validator(json.loads(contracts.joinpath("model-family-playbook.v1.schema.json").read_text()))
        method_schema = Draft202012Validator(json.loads(contracts.joinpath("analyst-workflow-method.v1.schema.json").read_text()))
        source_schema.validate(json.loads(data.joinpath("sources.json").read_text()))
        question_schema.validate(json.loads(data.joinpath("questions.json").read_text()))
        for path in data.joinpath("playbooks").iterdir():
            if path.name.endswith(".json"):
                playbook_schema.validate(json.loads(path.read_text()))
        for path in data.joinpath("methods").iterdir():
            if path.name.endswith(".json"):
                method_schema.validate(json.loads(path.read_text()))

    def test_playbooks_and_methods_are_provider_neutral_and_references_resolve(self) -> None:
        registry = KnowledgeRegistry.builtins()
        rendered = json.dumps(registry.to_dict(), sort_keys=True)
        for forbidden in ("provider_id", "package_id", "adapter_id", "sheet_layout"):
            self.assertNotIn(forbidden, rendered)
        sources = {item.source_id for item in registry.sources}
        questions = {item.question_id for item in registry.questions}
        for playbook in registry.playbooks:
            self.assertTrue(set(playbook.source_references).issubset(sources))
            self.assertTrue(set(playbook.question_ids).issubset(questions))
        for method in registry.methods:
            self.assertTrue(set(method.source_references).issubset(sources))
            for step in method.steps:
                self.assertTrue(set(step.source_references).issubset(set(method.source_references)))

    def test_methods_encode_ordered_analysis_and_commentary_boundary(self) -> None:
        registry = KnowledgeRegistry.builtins()
        for method in registry.methods:
            self.assertEqual([step.sequence for step in method.steps], list(range(1, len(method.steps) + 1)))
            stages = {step.stage for step in method.steps}
            self.assertIn("scope_decision", stages)
            self.assertIn("validation", stages)
            self.assertIn("outputs_kpis", stages)
            self.assertIn("commentary_evidence", stages)
            commentary = next(step for step in method.steps if step.stage == "commentary_evidence")
            self.assertEqual(commentary.execution_class, "governed_rule")
            self.assertIn("commentary_evidence", commentary.outputs)
            self.assertTrue(all(step.execution_class in {"source", "deterministic", "governed_rule", "judgment"} for step in method.steps))

    def test_reference_only_sources_are_not_promoted_to_accepted(self) -> None:
        registry = KnowledgeRegistry.builtins()
        for source in registry.sources:
            if source.license_status == "reference-only":
                self.assertEqual(source.review_state, "reference_only")

    def test_unknown_family_and_provider_specific_fields_fail_closed(self) -> None:
        payload = KnowledgeRegistry.builtins().playbooks[0].to_dict()
        payload["family_id"] = "unknown_family"
        with self.assertRaisesRegex(ValueError, "unknown family"):
            FamilyPlaybook.from_mapping(payload)
        payload = KnowledgeRegistry.builtins().playbooks[0].to_dict()
        payload["provider_id"] = "unsafe"
        with self.assertRaisesRegex(ValueError, "fields do not match"):
            FamilyPlaybook.from_mapping(payload)

        method = KnowledgeRegistry.builtins().methods[0].to_dict()
        method["family_id"] = "unknown_family"
        with self.assertRaisesRegex(ValueError, "unknown family"):
            AnalystWorkflowMethod.from_mapping(method)
        method = KnowledgeRegistry.builtins().methods[0].to_dict()
        method["provider_id"] = "unsafe"
        with self.assertRaisesRegex(ValueError, "fields do not match"):
            AnalystWorkflowMethod.from_mapping(method)

    def test_method_integrity_fails_closed(self) -> None:
        method = KnowledgeRegistry.builtins().methods[0].to_dict()
        method["steps"][1]["sequence"] = 7
        with self.assertRaisesRegex(ValueError, "contiguous and ordered"):
            AnalystWorkflowMethod.from_mapping(method)

        method = KnowledgeRegistry.builtins().methods[0].to_dict()
        method["steps"][0]["source_references"] = ["undeclared-source"]
        with self.assertRaisesRegex(ValueError, "declared by the method"):
            AnalystWorkflowMethod.from_mapping(method)

        method = KnowledgeRegistry.builtins().methods[0].to_dict()
        method["steps"][0]["formula"] = "=A1"
        with self.assertRaisesRegex(ValueError, "provider-specific field is forbidden"):
            AnalystWorkflowMethod.from_mapping(method)


if __name__ == "__main__":
    unittest.main()
