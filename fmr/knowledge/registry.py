from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from fmr.core.families import FAMILY_BY_ID
from fmr.core.handoffs import digest


_IDENTIFIER = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")
_SEMVER = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_FORBIDDEN_KEYS = {"adapter_id", "provider_id", "package_id", "formula", "coordinates", "sheet_layout"}


def _strings(value: Any, field: str, *, required: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field} must be an array of non-empty strings")
    cleaned = tuple(value)
    if required and not cleaned:
        raise ValueError(f"{field} must not be empty")
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{field} must not contain duplicates")
    return cleaned


def _assert_provider_neutral(value: Any, path: str = "playbook") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _FORBIDDEN_KEYS:
                raise ValueError(f"provider-specific field is forbidden at {path}.{key}")
            _assert_provider_neutral(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_provider_neutral(item, f"{path}[{index}]")


@dataclass(frozen=True)
class KnowledgeSource:
    source_id: str
    title: str
    publisher: str
    url: str
    retrieved_on: str
    usage: str
    license_status: str
    review_state: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "KnowledgeSource":
        expected = {"source_id", "title", "publisher", "url", "retrieved_on", "usage", "license_status", "review_state"}
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("knowledge source fields do not match the contract")
        if not isinstance(value.get("source_id"), str) or not _IDENTIFIER.fullmatch(value["source_id"]):
            raise ValueError("knowledge source_id is invalid")
        for field in ("title", "publisher", "url", "retrieved_on", "usage"):
            if not isinstance(value.get(field), str) or not value[field].strip():
                raise ValueError(f"knowledge source {field} is required")
        if value["license_status"] not in {"cc-by-4.0", "internal", "public-data-reference", "reference-only"}:
            raise ValueError("knowledge source license_status is invalid")
        if value["review_state"] not in {"accepted", "reference_only"}:
            raise ValueError("knowledge source review_state is invalid")
        return cls(**value)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ScopeQuestion:
    question_id: str
    prompt: str
    answer_type: str
    intent_field: str
    options: tuple[dict[str, str], ...]
    help_text: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ScopeQuestion":
        expected = {"question_id", "prompt", "answer_type", "intent_field", "options", "help_text"}
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("scope question fields do not match the contract")
        if not isinstance(value.get("question_id"), str) or not _IDENTIFIER.fullmatch(value["question_id"]):
            raise ValueError("question_id is invalid")
        if value.get("answer_type") not in {"boolean", "single_select"}:
            raise ValueError("question answer_type is invalid")
        for field in ("prompt", "intent_field", "help_text"):
            if not isinstance(value.get(field), str) or not value[field].strip():
                raise ValueError(f"scope question {field} is required")
        options = value.get("options")
        if not isinstance(options, list) or not options:
            raise ValueError("scope question options must be non-empty")
        if any(not isinstance(item, dict) or set(item) != {"value", "label"} or not all(isinstance(item[key], str) and item[key] for key in item) for item in options):
            raise ValueError("scope question option is invalid")
        if len({item["value"] for item in options}) != len(options):
            raise ValueError("scope question option values must be unique")
        return cls(value["question_id"], value["prompt"], value["answer_type"], value["intent_field"], tuple(options), value["help_text"])

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "options": [dict(item) for item in self.options]}


@dataclass(frozen=True)
class FamilyPlaybook:
    playbook_id: str
    version: str
    family_id: str
    title: str
    purpose: str
    business_questions: tuple[str, ...]
    does_not_answer: tuple[str, ...]
    appropriate_uses: tuple[str, ...]
    inappropriate_uses: tuple[str, ...]
    decision_contexts: tuple[str, ...]
    outcome_terms: tuple[str, ...]
    required_decisions: tuple[str, ...]
    required_data: tuple[str, ...]
    required_assumptions: tuple[str, ...]
    expected_outputs: tuple[str, ...]
    prerequisites: tuple[str, ...]
    follow_on_analyses: tuple[str, ...]
    common_misunderstandings: tuple[str, ...]
    limitations: tuple[str, ...]
    question_ids: tuple[str, ...]
    source_references: tuple[str, ...]
    review_state: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "FamilyPlaybook":
        expected = {"contract_version", "playbook_id", "version", "family_id", "title", "purpose", "business_questions", "does_not_answer", "appropriate_uses", "inappropriate_uses", "decision_contexts", "outcome_terms", "required_decisions", "required_data", "required_assumptions", "expected_outputs", "prerequisites", "follow_on_analyses", "common_misunderstandings", "limitations", "question_ids", "source_references", "review_state"}
        if not isinstance(value, dict) or set(value) != expected or value.get("contract_version") != "model-family-playbook.v1":
            raise ValueError("family playbook fields do not match the contract")
        _assert_provider_neutral(value)
        for field in ("playbook_id", "family_id"):
            if not isinstance(value.get(field), str) or not _IDENTIFIER.fullmatch(value[field]):
                raise ValueError(f"family playbook {field} is invalid")
        if value["family_id"] not in FAMILY_BY_ID:
            raise ValueError("family playbook references an unknown family")
        if not isinstance(value.get("version"), str) or not _SEMVER.fullmatch(value["version"]):
            raise ValueError("family playbook version is invalid")
        for field in ("title", "purpose"):
            if not isinstance(value.get(field), str) or not value[field].strip():
                raise ValueError(f"family playbook {field} is required")
        string_fields = ("business_questions", "does_not_answer", "appropriate_uses", "inappropriate_uses", "decision_contexts", "outcome_terms", "required_decisions", "required_data", "required_assumptions", "expected_outputs", "prerequisites", "follow_on_analyses", "common_misunderstandings", "limitations", "question_ids", "source_references")
        normalized = {field: _strings(value.get(field), field, required=field not in {"prerequisites", "follow_on_analyses"}) for field in string_fields}
        if value.get("review_state") not in {"synthetic_reviewed", "practitioner_accepted"}:
            raise ValueError("family playbook review_state is invalid")
        return cls(value["playbook_id"], value["version"], value["family_id"], value["title"], value["purpose"], *(normalized[field] for field in string_fields), value["review_state"])

    def to_dict(self) -> dict[str, Any]:
        return {"contract_version": "model-family-playbook.v1", **{key: ([*value] if isinstance(value, tuple) else value) for key, value in self.__dict__.items()}}


class KnowledgeRegistry:
    def __init__(self, *, version: str, sources: tuple[KnowledgeSource, ...], questions: tuple[ScopeQuestion, ...], playbooks: tuple[FamilyPlaybook, ...]) -> None:
        if not _SEMVER.fullmatch(version):
            raise ValueError("knowledge base version is invalid")
        for name, values, identifier in (("source", sources, "source_id"), ("question", questions, "question_id"), ("playbook", playbooks, "playbook_id")):
            ids = [getattr(item, identifier) for item in values]
            if len(ids) != len(set(ids)):
                raise ValueError(f"knowledge {name} IDs must be unique")
        families = [item.family_id for item in playbooks]
        if set(families) != set(FAMILY_BY_ID) or len(families) != len(set(families)):
            raise ValueError("knowledge registry must contain exactly one playbook for every registered family")
        source_ids, question_ids = {item.source_id for item in sources}, {item.question_id for item in questions}
        for playbook in playbooks:
            if not set(playbook.source_references).issubset(source_ids):
                raise ValueError("playbook references an unknown knowledge source")
            if not set(playbook.question_ids).issubset(question_ids):
                raise ValueError("playbook references an unknown scope question")
            family = FAMILY_BY_ID[playbook.family_id]
            if not set(family.required_deliverables).issubset(playbook.expected_outputs):
                raise ValueError("playbook outputs do not cover its model-family definition")
        self.version, self.sources, self.questions, self.playbooks = version, tuple(sorted(sources, key=lambda item: item.source_id)), tuple(sorted(questions, key=lambda item: item.question_id)), tuple(sorted(playbooks, key=lambda item: item.family_id))
        self.sha256 = digest(self.to_dict(include_hash=False))

    @classmethod
    def builtins(cls) -> "KnowledgeRegistry":
        root = files("fmr.knowledge.data")
        source_payload = json.loads(root.joinpath("sources.json").read_text(encoding="utf-8"))
        question_payload = json.loads(root.joinpath("questions.json").read_text(encoding="utf-8"))
        if set(source_payload) != {"contract_version", "knowledge_base_version", "sources"} or source_payload.get("contract_version") != "knowledge-source-registry.v1":
            raise ValueError("knowledge source registry fields do not match the contract")
        if set(question_payload) != {"contract_version", "version", "questions"} or question_payload.get("contract_version") != "scope-question-set.v1":
            raise ValueError("scope question set fields do not match the contract")
        if question_payload["version"] != source_payload["knowledge_base_version"]:
            raise ValueError("knowledge source and question versions must match")
        playbook_root = root.joinpath("playbooks")
        playbooks = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(playbook_root.iterdir(), key=lambda item: item.name) if path.name.endswith(".json")]
        return cls(
            version=source_payload["knowledge_base_version"],
            sources=tuple(KnowledgeSource.from_mapping(item) for item in source_payload["sources"]),
            questions=tuple(ScopeQuestion.from_mapping(item) for item in question_payload["questions"]),
            playbooks=tuple(FamilyPlaybook.from_mapping(item) for item in playbooks),
        )

    def playbook(self, family_id: str) -> FamilyPlaybook:
        return next(item for item in self.playbooks if item.family_id == family_id)

    def question(self, question_id: str) -> ScopeQuestion:
        return next(item for item in self.questions if item.question_id == question_id)

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        value = {"contract_version": "modelling-knowledge-registry.v1", "version": self.version, "sources": [item.to_dict() for item in self.sources], "questions": [item.to_dict() for item in self.questions], "playbooks": [item.to_dict() for item in self.playbooks]}
        return {**value, "sha256": self.sha256} if include_hash else value
