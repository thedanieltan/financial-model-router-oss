from __future__ import annotations

import copy
import json
import unittest
from importlib.resources import files

from jsonschema import Draft202012Validator

from fmr.core import FAMILIES
from fmr.knowledge import FamilyPlaybook, KnowledgeRegistry


class ModelKnowledgeTests(unittest.TestCase):
    def test_builtins_cover_registered_families_and_are_deterministic(self) -> None:
        first = KnowledgeRegistry.builtins()
        second = KnowledgeRegistry.builtins()
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual({item.family_id for item in first.playbooks}, {item.family_id for item in FAMILIES})
        self.assertTrue(all(item.review_state == "synthetic_reviewed" for item in first.playbooks))
        self.assertEqual(len(first.sources), 4)
        self.assertEqual(len(first.questions), 5)

    def test_bundled_knowledge_files_validate_against_json_schema(self) -> None:
        contracts = files("fmr.contracts")
        data = files("fmr.knowledge.data")
        source_schema = Draft202012Validator(json.loads(contracts.joinpath("knowledge-source-registry.v1.schema.json").read_text()))
        question_schema = Draft202012Validator(json.loads(contracts.joinpath("scope-question-set.v1.schema.json").read_text()))
        playbook_schema = Draft202012Validator(json.loads(contracts.joinpath("model-family-playbook.v1.schema.json").read_text()))
        source_schema.validate(json.loads(data.joinpath("sources.json").read_text()))
        question_schema.validate(json.loads(data.joinpath("questions.json").read_text()))
        for path in data.joinpath("playbooks").iterdir():
            if path.name.endswith(".json"):
                playbook_schema.validate(json.loads(path.read_text()))

    def test_playbooks_are_provider_neutral_and_references_resolve(self) -> None:
        registry = KnowledgeRegistry.builtins()
        rendered = json.dumps(registry.to_dict(), sort_keys=True)
        for forbidden in ("provider_id", "package_id", "adapter_id", "sheet_layout"):
            self.assertNotIn(forbidden, rendered)
        sources = {item.source_id for item in registry.sources}
        questions = {item.question_id for item in registry.questions}
        for playbook in registry.playbooks:
            self.assertTrue(set(playbook.source_references).issubset(sources))
            self.assertTrue(set(playbook.question_ids).issubset(questions))

    def test_unknown_family_and_provider_specific_fields_fail_closed(self) -> None:
        payload = KnowledgeRegistry.builtins().playbooks[0].to_dict()
        payload["family_id"] = "unknown_family"
        with self.assertRaisesRegex(ValueError, "unknown family"):
            FamilyPlaybook.from_mapping(payload)
        payload = KnowledgeRegistry.builtins().playbooks[0].to_dict()
        payload["provider_id"] = "unsafe"
        with self.assertRaisesRegex(ValueError, "fields do not match"):
            FamilyPlaybook.from_mapping(payload)


if __name__ == "__main__":
    unittest.main()
