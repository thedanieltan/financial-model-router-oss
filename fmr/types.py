from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ModelRequest:
    objective: str
    role: str
    available_data: tuple[str, ...]
    workbook_capabilities: tuple[str, ...]
    assumptions: tuple[str, ...]
    contract_version: str = "model-request.v1"

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ModelRequest":
        if data.get("contract_version") != "model-request.v1":
            raise ValueError("unsupported contract_version")
        objective = data.get("objective")
        role = data.get("role")
        if not isinstance(objective, str) or not objective.strip():
            raise ValueError("objective must be a non-empty string")
        if not isinstance(role, str) or not role.strip():
            raise ValueError("role must be a non-empty string")
        return cls(
            objective=objective.strip(),
            role=role.strip(),
            available_data=_string_tuple(data.get("available_data"), "available_data"),
            workbook_capabilities=_string_tuple(
                data.get("workbook_capabilities"),
                "workbook_capabilities",
            ),
            assumptions=_string_tuple(data.get("assumptions"), "assumptions"),
        )


@dataclass(frozen=True)
class ModelDefinition:
    model_family: str
    title: str
    objective_terms: tuple[str, ...]
    required_data: tuple[str, ...]
    required_assumptions: tuple[str, ...]
    required_workbook_capabilities: tuple[str, ...]
    operations: tuple[str, ...]


@dataclass(frozen=True)
class ReadinessReport:
    ready: bool
    available_data: tuple[str, ...]
    missing_data: tuple[str, ...]
    available_assumptions: tuple[str, ...]
    missing_assumptions: tuple[str, ...]
    available_workbook_capabilities: tuple[str, ...]
    missing_workbook_capabilities: tuple[str, ...]
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "available_data": list(self.available_data),
            "missing_data": list(self.missing_data),
            "available_assumptions": list(self.available_assumptions),
            "missing_assumptions": list(self.missing_assumptions),
            "available_workbook_capabilities": list(
                self.available_workbook_capabilities
            ),
            "missing_workbook_capabilities": list(
                self.missing_workbook_capabilities
            ),
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class Recommendation:
    contract_version: str
    model_family: str
    title: str
    confidence: str
    reasons: tuple[str, ...]
    readiness: ReadinessReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "model_family": self.model_family,
            "title": self.title,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
            "readiness": self.readiness.to_dict(),
        }


@dataclass(frozen=True)
class TransformationOperation:
    sequence: int
    operation: str
    target: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TransformationPlan:
    contract_version: str
    model_family: str
    ready_to_apply: bool
    operations: tuple[TransformationOperation, ...]
    unresolved_inputs: tuple[str, ...]
    controls: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "model_family": self.model_family,
            "ready_to_apply": self.ready_to_apply,
            "operations": [operation.to_dict() for operation in self.operations],
            "unresolved_inputs": list(self.unresolved_inputs),
            "controls": list(self.controls),
        }


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be an array of strings")
    cleaned = {item.strip() for item in value if item.strip()}
    return tuple(sorted(cleaned))
