from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fmr.core import ModelJob, RoutingPolicy, route_job
from fmr.registry import ProviderRegistry
from fmr.vocabulary import VocabularyRegistry


def _strings(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{field} must be an array of non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{field} must not contain duplicates")
    return tuple(value)


@dataclass(frozen=True)
class OrganizationPolicy:
    organization_id: str
    version: str
    private_provider_directories: tuple[str, ...]
    private_vocabulary_directories: tuple[str, ...]
    allowed_providers: tuple[str, ...]
    provider_precedence: tuple[str, ...]
    approved_provider_versions: tuple[str, ...]
    approved_package_versions: tuple[str, ...]
    prohibited_execution_modes: tuple[str, ...]
    approved_template_ids: tuple[str, ...]
    require_approved_template: bool
    local_only: bool
    audit_retention_days: int
    contract_version: str = "organization-routing-policy.v1"

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "OrganizationPolicy":
        fields = {
            "contract_version", "organization_id", "version", "private_provider_directories",
            "private_vocabulary_directories", "allowed_providers", "provider_precedence",
            "approved_provider_versions", "approved_package_versions", "prohibited_execution_modes",
            "approved_template_ids", "require_approved_template", "local_only", "audit_retention_days",
        }
        if not isinstance(value, dict) or set(value) != fields or value.get("contract_version") != "organization-routing-policy.v1":
            raise ValueError("organization routing policy fields do not match the contract")
        if not isinstance(value.get("organization_id"), str) or not re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*", value["organization_id"]):
            raise ValueError("organization_id is invalid")
        if not isinstance(value.get("version"), str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value["version"]):
            raise ValueError("organization policy version is invalid")
        for field in ("require_approved_template", "local_only"):
            if not isinstance(value.get(field), bool):
                raise ValueError(f"{field} must be a boolean")
        retention = value.get("audit_retention_days")
        if not isinstance(retention, int) or isinstance(retention, bool) or retention < 1:
            raise ValueError("audit_retention_days must be a positive integer")
        result = cls(
            value["organization_id"], value["version"],
            _strings(value["private_provider_directories"], "private_provider_directories"),
            _strings(value["private_vocabulary_directories"], "private_vocabulary_directories"),
            _strings(value["allowed_providers"], "allowed_providers"),
            _strings(value["provider_precedence"], "provider_precedence"),
            _strings(value["approved_provider_versions"], "approved_provider_versions"),
            _strings(value["approved_package_versions"], "approved_package_versions"),
            _strings(value["prohibited_execution_modes"], "prohibited_execution_modes"),
            _strings(value["approved_template_ids"], "approved_template_ids"),
            value["require_approved_template"], value["local_only"], retention,
        )
        if set(result.prohibited_execution_modes) - {"local", "remote", "handoff_only"}:
            raise ValueError("prohibited_execution_modes contains an unsupported mode")
        if set(result.provider_precedence) - set(result.allowed_providers):
            raise ValueError("provider_precedence must contain only allowed providers")
        return result

    @classmethod
    def from_file(cls, path: str | Path) -> "OrganizationPolicy":
        return cls.from_mapping(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version, "organization_id": self.organization_id,
            "version": self.version, "private_provider_directories": list(self.private_provider_directories),
            "private_vocabulary_directories": list(self.private_vocabulary_directories),
            "allowed_providers": list(self.allowed_providers), "provider_precedence": list(self.provider_precedence),
            "approved_provider_versions": list(self.approved_provider_versions),
            "approved_package_versions": list(self.approved_package_versions),
            "prohibited_execution_modes": list(self.prohibited_execution_modes),
            "approved_template_ids": list(self.approved_template_ids),
            "require_approved_template": self.require_approved_template, "local_only": self.local_only,
            "audit_retention_days": self.audit_retention_days,
        }

    @property
    def policy_sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def effective_policy(self, base: RoutingPolicy) -> RoutingPolicy:
        precedence = self.provider_precedence + tuple(item for item in base.preferred_providers if item not in self.provider_precedence)
        return RoutingPolicy(
            f"organization:{self.organization_id}@{self.version}+{base.version}",
            base.require_local or self.local_only, precedence, dict(base.weights), self.organization_id,
            self.allowed_providers, self.approved_provider_versions, self.approved_package_versions,
            self.prohibited_execution_modes, self.approved_template_ids, self.require_approved_template,
            self.audit_retention_days,
        )

    def registry(self) -> ProviderRegistry:
        return ProviderRegistry.discover(manifest_directories=self.private_provider_directories)

    def vocabulary(self) -> VocabularyRegistry:
        return VocabularyRegistry.discover(self.private_vocabulary_directories)

    def normalize_job(self, value: dict[str, Any]) -> ModelJob:
        normalized = dict(value)
        industry = normalized.get("industry")
        if isinstance(industry, str):
            normalized["industry"] = self.vocabulary().normalize_industry(industry)
        return ModelJob.from_mapping(normalized)


def route_organization_job(job: dict[str, Any] | ModelJob, organization_policy: OrganizationPolicy, *, base_policy: RoutingPolicy) -> dict[str, Any]:
    model_job = organization_policy.normalize_job(job) if isinstance(job, dict) else job
    return route_job(model_job, registry=organization_policy.registry(), policy=organization_policy.effective_policy(base_policy))
