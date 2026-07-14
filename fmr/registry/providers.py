from __future__ import annotations

import json
import re
import importlib.util
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, Iterable

_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def _required_string(data: dict[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _strings(data: dict[str, Any], field: str, *, required: bool = False) -> tuple[str, ...]:
    value = data.get(field, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field} must be an array of non-empty strings")
    result = tuple(sorted(set(value)))
    if required and not result:
        raise ValueError(f"{field} must contain at least one item")
    return result


@dataclass(frozen=True)
class ModelPackageManifest:
    contract_version: str
    package_id: str
    version: str
    model_family: str
    industries: tuple[str, ...]
    deliverables: tuple[str, ...]
    required_data: tuple[str, ...]
    required_assumptions: tuple[str, ...]
    accepted_inputs: tuple[str, ...]
    output_artifacts: tuple[str, ...]
    output_formats: tuple[str, ...]
    validation_checks: tuple[str, ...]
    execution_capabilities: tuple[str, ...]
    adapter_id: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ModelPackageManifest":
        if not isinstance(data, dict):
            raise ValueError("package manifest must be an object")
        if data.get("contract_version") != "model-package-manifest.v1":
            raise ValueError("unsupported model package manifest contract")
        version = _required_string(data, "version")
        if not _SEMVER.fullmatch(version):
            raise ValueError("package version must use MAJOR.MINOR.PATCH")
        return cls(
            contract_version="model-package-manifest.v1", package_id=_required_string(data, "package_id"), version=version,
            model_family=_required_string(data, "model_family"),
            industries=_strings(data, "industries", required=True),
            deliverables=_strings(data, "deliverables", required=True),
            required_data=_strings(data, "required_data"),
            required_assumptions=_strings(data, "required_assumptions"),
            accepted_inputs=_strings(data, "accepted_inputs"),
            output_artifacts=_strings(data, "output_artifacts", required=True),
            output_formats=_strings(data, "output_formats", required=True),
            validation_checks=_strings(data, "validation_checks", required=True),
            execution_capabilities=_strings(data, "execution_capabilities", required=True),
            adapter_id=_required_string(data, "adapter_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {key: list(value) if isinstance(value, tuple) else value for key, value in self.__dict__.items()}


@dataclass(frozen=True)
class ProviderManifest:
    provider_id: str
    version: str
    execution_mode: str
    network_required: bool
    license: str
    open_source: bool
    privacy_behavior: tuple[str, ...]
    runtime_dependencies: tuple[str, ...]
    determinism_level: str
    validation_capabilities: tuple[str, ...]
    limitations: tuple[str, ...]
    packages: tuple[ModelPackageManifest, ...]
    contract_version: str = "provider-manifest.v1"

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ProviderManifest":
        if not isinstance(data, dict) or data.get("contract_version") != "provider-manifest.v1":
            raise ValueError("unsupported provider manifest contract")
        version = _required_string(data, "version")
        if not _SEMVER.fullmatch(version):
            raise ValueError("provider version must use MAJOR.MINOR.PATCH")
        mode = _required_string(data, "execution_mode")
        if mode not in {"local", "remote", "handoff_only"}:
            raise ValueError("execution_mode is not supported")
        if not isinstance(data.get("network_required"), bool) or not isinstance(data.get("open_source"), bool):
            raise ValueError("network_required and open_source must be booleans")
        raw_packages = data.get("packages")
        if not isinstance(raw_packages, list) or not raw_packages:
            raise ValueError("packages must be a non-empty array")
        packages = tuple(ModelPackageManifest.from_mapping(item) for item in raw_packages)
        if len({item.package_id for item in packages}) != len(packages):
            raise ValueError("package IDs must be unique within a provider")
        provider_id = _required_string(data, "provider_id")
        if any(not item.package_id.startswith(provider_id + "/") for item in packages):
            raise ValueError("package IDs must be namespaced by provider_id")
        return cls(
            provider_id=provider_id, version=version, execution_mode=mode,
            network_required=data["network_required"], license=_required_string(data, "license"),
            open_source=data["open_source"], privacy_behavior=_strings(data, "privacy_behavior", required=True),
            runtime_dependencies=_strings(data, "runtime_dependencies"),
            determinism_level=_required_string(data, "determinism_level"),
            validation_capabilities=_strings(data, "validation_capabilities", required=True),
            limitations=_strings(data, "limitations"), packages=packages,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version, "provider_id": self.provider_id,
            "version": self.version, "execution_mode": self.execution_mode,
            "network_required": self.network_required, "license": self.license,
            "open_source": self.open_source, "privacy_behavior": list(self.privacy_behavior),
            "runtime_dependencies": list(self.runtime_dependencies), "determinism_level": self.determinism_level,
            "validation_capabilities": list(self.validation_capabilities), "limitations": list(self.limitations),
            "packages": [item.to_dict() for item in self.packages],
        }


@dataclass(frozen=True)
class RegisteredPackage:
    provider: ProviderManifest
    package: ModelPackageManifest
    runtime_available: bool
    provider_adapter_available: bool


class ProviderRegistry:
    def __init__(self, providers: Iterable[ProviderManifest], *, runtime_availability: dict[str, bool] | None = None, installed_adapter_ids: Iterable[str] = ()) -> None:
        provider_list = tuple(providers)
        if len({item.provider_id for item in provider_list}) != len(provider_list):
            raise ValueError("provider IDs must be unique")
        self._providers = {item.provider_id: item for item in provider_list}
        self._runtime = dict(runtime_availability or {})
        self._adapter_ids = frozenset(installed_adapter_ids)

    @classmethod
    def builtins(cls, *, disabled_providers: Iterable[str] = (), runtime_availability: dict[str, bool] | None = None) -> "ProviderRegistry":
        disabled = set(disabled_providers)
        manifests = []
        root = files("fmr.providers")
        for provider_name in ("native_xlsx", "reference_handoff"):
            data = json.loads(root.joinpath(provider_name, "manifest.json").read_text(encoding="utf-8"))
            manifest = ProviderManifest.from_mapping(data)
            if manifest.provider_id not in disabled:
                manifests.append(manifest)
        availability = {"native-xlsx": importlib.util.find_spec("openpyxl") is not None, "reference-handoff": True}
        availability.update(runtime_availability or {})
        from fmr.provider_adapters import AVAILABLE_PROVIDER_ADAPTERS
        return cls(manifests, runtime_availability=availability, installed_adapter_ids=AVAILABLE_PROVIDER_ADAPTERS)

    def providers(self) -> tuple[ProviderManifest, ...]:
        return tuple(self._providers[key] for key in sorted(self._providers))

    def packages(self, family_id: str | None = None) -> tuple[RegisteredPackage, ...]:
        result = []
        for provider in self.providers():
            for package in provider.packages:
                if family_id is None or package.model_family == family_id:
                    result.append(RegisteredPackage(provider, package, self._runtime.get(provider.provider_id, True), package.adapter_id in self._adapter_ids))
        return tuple(sorted(result, key=lambda item: (item.provider.provider_id, item.package.package_id, item.package.version)))

    def package(self, provider_id: str, package_id: str) -> RegisteredPackage:
        for item in self.packages():
            if item.provider.provider_id == provider_id and item.package.package_id == package_id:
                return item
        raise KeyError((provider_id, package_id))
