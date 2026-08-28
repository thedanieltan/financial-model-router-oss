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
_METHOD_STAGES = {
    "scope_decision",
    "source_history",
    "normalize_reconcile",
    "assumptions_drivers",
    "model_structure",
    "supporting_schedules",
    "core_model",
    "validation",
    "scenario_sensitivity",
    "outputs_kpis",
    "variance_driver_analysis",
    "commentary_evidence",
}
_EXECUTION_CLASSES = {"source", "deterministic", "governed_rule", "judgment"}
_REQUIREMENT_CLASSES = {"universal", "common_default", "conditional", "method_variant"}


def _strings(value: Any, field: str, *, required: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field} must be an array of non-empty strings")
    cleaned = tuple(value)
    if required and not cleaned:
        raise ValueError(f"{field} must not be empty")
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{field} must not contain duplicates")
    return cleaned


def _assert_provider_neutral(value: Any, path: str = "knowledge") -> None:
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
        _assert_provider_neutral(value, "playbook")
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


@dataclass(frozen=True)
class WorkflowStep:
    step_id: str
    sequence: int
    stage: str
    purpose: str
    execution_class: str
    requirement_class: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    checks: tuple[str, ...]
    conditions: tuple[str, ...]
    source_references: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "WorkflowStep":
        expected = {"step_id", "sequence", "stage", "purpose", "execution_class", "requirement_class", "inputs", "outputs", "checks", "conditions", "source_references"}
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("workflow step fields do not match the contract")
        _assert_provider_neutral(value, "workflow_step")
        if not isinstance(value.get("step_id"), str) or not _IDENTIFIER.fullmatch(value["step_id"]):
            raise ValueError("workflow step_id is invalid")
        if not isinstance(value.get("sequence"), int) or isinstance(value["sequence"], bool) or value["sequence"] < 1:
            raise ValueError("workflow sequence is invalid")
        if value.get("stage") not in _METHOD_STAGES:
            raise ValueError("workflow stage is invalid")
        if not isinstance(value.get("purpose"), str) or not value["purpose"].strip():
            raise ValueError("workflow purpose is required")
        if value.get("execution_class") not in _EXECUTION_CLASSES:
            raise ValueError("workflow execution_class is invalid")
        if value.get("requirement_class") not in _REQUIREMENT_CLASSES:
            raise ValueError("workflow requirement_class is invalid")
        normalized = {field: _strings(value.get(field), field, required=field == "source_references") for field in ("inputs", "outputs", "checks", "conditions", "source_references")}
        return cls(value["step_id"], value["sequence"], value["stage"], value["purpose"], value["execution_class"], value["requirement_class"], normalized["inputs"], normalized["outputs"], normalized["checks"], normalized["conditions"], normalized["source_references"])

    def to_dict(self) -> dict[str, Any]:
        return {key: ([*value] if isinstance(value, tuple) else value) for key, value in self.__dict__.items()}


@dataclass(frozen=True)
class AnalystWorkflowMethod:
    method_id: str
    version: str
    family_id: str
    title: str
    objective: str
    steps: tuple[WorkflowStep, ...]
    source_references: tuple[str, ...]
    review_state: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "AnalystWorkflowMethod":
        expected = {"contract_version", "method_id", "version", "family_id", "title", "objective", "steps", "source_references", "review_state"}
        if not isinstance(value, dict) or set(value) != expected or value.get("contract_version") != "analyst-workflow-method.v1":
            raise ValueError("analyst workflow method fields do not match the contract")
        _assert_provider_neutral(value, "analyst_workflow_method")
        for field in ("method_id", "family_id"):
            if not isinstance(value.get(field), str) or not _IDENTIFIER.fullmatch(value[field]):
                raise ValueError(f"analyst workflow method {field} is invalid")
        if value["family_id"] not in FAMILY_BY_ID:
            raise ValueError("analyst workflow method references an unknown family")
        if not isinstance(value.get("version"), str) or not _SEMVER.fullmatch(value["version"]):
            raise ValueError("analyst workflow method version is invalid")
        for field in ("title", "objective"):
            if not isinstance(value.get(field), str) or not value[field].strip():
                raise ValueError(f"analyst workflow method {field} is required")
        raw_steps = value.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("analyst workflow method steps must be non-empty")
        steps = tuple(WorkflowStep.from_mapping(item) for item in raw_steps)
        step_ids = [item.step_id for item in steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("analyst workflow step IDs must be unique")
        if [item.sequence for item in steps] != list(range(1, len(steps) + 1)):
            raise ValueError("analyst workflow sequences must be contiguous and ordered")
        source_references = _strings(value.get("source_references"), "source_references")
        for step in steps:
            if not set(step.source_references).issubset(source_references):
                raise ValueError("workflow step source references must be declared by the method")
        if value.get("review_state") not in {"reference_grounded", "practitioner_accepted"}:
            raise ValueError("analyst workflow method review_state is invalid")
        return cls(value["method_id"], value["version"], value["family_id"], value["title"], value["objective"], steps, source_references, value["review_state"])

    def to_dict(self) -> dict[str, Any]:
        return {"contract_version": "analyst-workflow-method.v1", "method_id": self.method_id, "version": self.version, "family_id": self.family_id, "title": self.title, "objective": self.objective, "steps": [item.to_dict() for item in self.steps], "source_references": [*self.source_references], "review_state": self.review_state}


class KnowledgeRegistry:
    def __init__(self, *, version: str, sources: tuple[KnowledgeSource, ...], questions: tuple[ScopeQuestion, ...], playbooks: tuple[FamilyPlaybook, ...], methods: tuple[AnalystWorkflowMethod, ...]) -> None:
        if not _SEMVER.fullmatch(version):
            raise ValueError("knowledge base version is invalid")
        for name, values, identifier in (("source", sources, "source_id"), ("question", questions, "question_id"), ("playbook", playbooks, "playbook_id"), ("method", methods, "method_id")):
            ids = [getattr(item, identifier) for item in values]
            if len(ids) != len(set(ids)):
                raise ValueError(f"knowledge {name} IDs must be unique")
        families = [item.family_id for item in playbooks]
        if set(families) != set(FAMILY_BY_ID) or len(families) != len(set(families)):
            raise ValueError("knowledge registry must contain exactly one playbook for every registered family")
        method_families = [item.family_id for item in methods]
        if set(method_families) != set(FAMILY_BY_ID) or len(method_families) != len(set(method_families)):
            raise ValueError("knowledge registry must contain exactly one analyst workflow method for every registered family")
        source_ids, question_ids = {item.source_id for item in sources}, {item.question_id for item in questions}
        for playbook in playbooks:
            if not set(playbook.source_references).issubset(source_ids):
                raise ValueError("playbook references an unknown knowledge source")
            if not set(playbook.question_ids).issubset(question_ids):
                raise ValueError("playbook references an unknown scope question")
            family = FAMILY_BY_ID[playbook.family_id]
            if not set(family.required_deliverables).issubset(playbook.expected_outputs):
                raise ValueError("playbook outputs do not cover its model-family definition")
        for method in methods:
            if not set(method.source_references).issubset(source_ids):
                raise ValueError("analyst workflow method references an unknown knowledge source")
        self.version = version
        self.sources = tuple(sorted(sources, key=lambda item: item.source_id))
        self.questions = tuple(sorted(questions, key=lambda item: item.question_id))
        self.playbooks = tuple(sorted(playbooks, key=lambda item: item.family_id))
        self.methods = tuple(sorted(methods, key=lambda item: item.family_id))
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
        method_root = root.joinpath("methods")
        methods = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(method_root.iterdir(), key=lambda item: item.name) if path.name.endswith(".json")]
        return cls(version=source_payload["knowledge_base_version"], sources=tuple(KnowledgeSource.from_mapping(item) for item in source_payload["sources"]), questions=tuple(ScopeQuestion.from_mapping(item) for item in question_payload["questions"]), playbooks=tuple(FamilyPlaybook.from_mapping(item) for item in playbooks), methods=tuple(AnalystWorkflowMethod.from_mapping(item) for item in methods))

    def playbook(self, family_id: str) -> FamilyPlaybook:
        return next(item for item in self.playbooks if item.family_id == family_id)

    def method(self, family_id: str) -> AnalystWorkflowMethod:
        return next(item for item in self.methods if item.family_id == family_id)

    def question(self, question_id: str) -> ScopeQuestion:
        return next(item for item in self.questions if item.question_id == question_id)

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        value = {"contract_version": "modelling-knowledge-registry.v1", "version": self.version, "sources": [item.to_dict() for item in self.sources], "questions": [item.to_dict() for item in self.questions], "playbooks": [item.to_dict() for item in self.playbooks], "methods": [item.to_dict() for item in self.methods]}
        return {**value, "sha256": self.sha256} if include_hash else value
