from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from fmr.vocabulary import VocabularyRegistry


def _strings(value: Any, field: str, *, required: bool = False) -> tuple[str, ...]:
    if value is None:
        value = []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field} must be an array of strings")
    cleaned_values = [item.strip() for item in value]
    if len(set(cleaned_values)) != len(cleaned_values):
        raise ValueError(f"{field} must not contain duplicates")
    cleaned = tuple(sorted(cleaned_values))
    if required and not cleaned:
        raise ValueError(f"{field} must contain at least one item")
    return cleaned


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return dict(value)


@dataclass(frozen=True)
class JobConstraints:
    local_only: bool = False
    open_source_only: bool = False
    network_allowed: bool = True
    allowed_providers: tuple[str, ...] = ()
    prohibited_providers: tuple[str, ...] = ()
    pinned_provider_versions: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Any) -> "JobConstraints":
        data = _mapping(value, "constraints")
        allowed = {"local_only", "open_source_only", "network_allowed", "allowed_providers", "prohibited_providers", "pinned_provider_versions"}
        if set(data) - allowed:
            raise ValueError("constraints contains unsupported fields")
        for field in ("local_only", "open_source_only", "network_allowed"):
            if field in data and not isinstance(data[field], bool):
                raise ValueError(f"constraints.{field} must be a boolean")
        return cls(
            local_only=data.get("local_only", False),
            open_source_only=data.get("open_source_only", False),
            network_allowed=data.get("network_allowed", True),
            allowed_providers=_strings(data.get("allowed_providers"), "constraints.allowed_providers"),
            prohibited_providers=_strings(data.get("prohibited_providers"), "constraints.prohibited_providers"),
            pinned_provider_versions=_strings(data.get("pinned_provider_versions"), "constraints.pinned_provider_versions"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_only": self.local_only,
            "open_source_only": self.open_source_only,
            "network_allowed": self.network_allowed,
            "allowed_providers": list(self.allowed_providers),
            "prohibited_providers": list(self.prohibited_providers),
            "pinned_provider_versions": list(self.pinned_provider_versions),
        }


@dataclass(frozen=True)
class ModelJob:
    objective: str
    requested_deliverables: tuple[str, ...]
    model_family: str | None
    industry: str | None
    context: dict[str, Any]
    available_data: tuple[str, ...]
    available_assumptions: tuple[str, ...]
    input_references: dict[str, Any]
    existing_model: dict[str, Any]
    output_formats: tuple[str, ...]
    constraints: JobConstraints
    privacy_constraints: tuple[str, ...]
    licensing_constraints: tuple[str, ...]
    preferred_execution_mode: str | None
    contract_version: str = "model-job.v2"

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ModelJob":
        if not isinstance(data, dict):
            raise ValueError("model job must be an object")
        if data.get("contract_version") != "model-job.v2":
            raise ValueError("unsupported contract_version")
        allowed = {
            "contract_version", "objective", "requested_deliverables", "model_family", "industry", "context",
            "available_data", "available_assumptions", "input_references", "existing_model", "output_formats",
            "constraints", "privacy_constraints", "licensing_constraints", "preferred_execution_mode",
        }
        if set(data) - allowed:
            raise ValueError("model job contains unsupported fields")
        objective = data.get("objective")
        if not isinstance(objective, str) or not objective.strip():
            raise ValueError("objective must be a non-empty string")
        family = data.get("model_family")
        if family is not None and (not isinstance(family, str) or not family.strip()):
            raise ValueError("model_family must be a non-empty string when supplied")
        industry = data.get("industry")
        if industry is not None and (not isinstance(industry, str) or not industry.strip()):
            raise ValueError("industry must be a non-empty string when supplied")
        mode = data.get("preferred_execution_mode")
        if mode is not None and mode not in {"local", "remote", "handoff_only"}:
            raise ValueError("preferred_execution_mode is not supported")
        input_references = _mapping(data.get("input_references"), "input_references")
        for name, reference in input_references.items():
            if not isinstance(reference, dict):
                raise ValueError(f"input_references.{name} must be an object")
            allowed_reference = {"contract_version", "sha256", "path", "uri"}
            if set(reference) - allowed_reference:
                raise ValueError(f"input_references.{name} contains unsupported fields")
            if not isinstance(reference.get("contract_version"), str) or not reference["contract_version"]:
                raise ValueError(f"input_references.{name}.contract_version is required")
            if not isinstance(reference.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", reference["sha256"]):
                raise ValueError(f"input_references.{name}.sha256 is invalid")
            locations = [key for key in ("path", "uri") if isinstance(reference.get(key), str) and reference[key]]
            if not locations:
                raise ValueError(f"input_references.{name} requires path or uri")
        output_formats = _strings(data.get("output_formats"), "output_formats", required=True)
        if any(not re.fullmatch(r"[a-z0-9][a-z0-9._+-]*", item) for item in output_formats):
            raise ValueError("output_formats contains an invalid format identifier")
        return cls(
            objective=objective.strip(),
            requested_deliverables=_strings(data.get("requested_deliverables"), "requested_deliverables", required=True),
            model_family=family.strip() if family else None,
            industry=VocabularyRegistry.builtins().normalize_industry(industry) if industry else None,
            context=_mapping(data.get("context"), "context"),
            available_data=_strings(data.get("available_data"), "available_data"),
            available_assumptions=_strings(data.get("available_assumptions"), "available_assumptions"),
            input_references=input_references,
            existing_model=_mapping(data.get("existing_model"), "existing_model"),
            output_formats=output_formats,
            constraints=JobConstraints.from_mapping(data.get("constraints")),
            privacy_constraints=_strings(data.get("privacy_constraints"), "privacy_constraints"),
            licensing_constraints=_strings(data.get("licensing_constraints"), "licensing_constraints"),
            preferred_execution_mode=mode,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "objective": self.objective,
            "requested_deliverables": list(self.requested_deliverables),
            "model_family": self.model_family,
            "industry": self.industry,
            "context": self.context,
            "available_data": list(self.available_data),
            "available_assumptions": list(self.available_assumptions),
            "input_references": self.input_references,
            "existing_model": self.existing_model,
            "output_formats": list(self.output_formats),
            "constraints": self.constraints.to_dict(),
            "privacy_constraints": list(self.privacy_constraints),
            "licensing_constraints": list(self.licensing_constraints),
            "preferred_execution_mode": self.preferred_execution_mode,
        }
