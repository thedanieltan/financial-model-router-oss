from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import metadata
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterable

_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[a-z]+[0-9]+)?$")
_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_FORMAT = re.compile(r"^[a-z0-9][a-z0-9._+-]*$")


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
    if len(result) != len(value):
        raise ValueError(f"{field} must not contain duplicates")
    if required and not result:
        raise ValueError(f"{field} must contain at least one item")
    return result


@dataclass(frozen=True)
class ArtifactSpec:
    kind: str
    format: str
    required: bool = True

    @classmethod
    def from_mapping(cls, data: Any) -> "ArtifactSpec":
        if not isinstance(data, dict):
            raise ValueError("output_artifacts entries must be objects")
        if set(data) - {"kind", "format", "required"}:
            raise ValueError("output_artifacts entries contain unsupported fields")
        required = data.get("required", True)
        if not isinstance(required, bool):
            raise ValueError("output_artifacts.required must be a boolean")
        kind = _required_string(data, "kind")
        output_format = _required_string(data, "format")
        if not _IDENTIFIER.fullmatch(kind) or not _FORMAT.fullmatch(output_format):
            raise ValueError("output artifact kind or format is invalid")
        return cls(kind, output_format, required)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "format": self.format, "required": self.required}


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
    output_artifacts: tuple[ArtifactSpec, ...]
    output_formats: tuple[str, ...]
    validation_checks: tuple[str, ...]
    execution_capabilities: tuple[str, ...]
    adapter_id: str
    adapter_entry_point: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ModelPackageManifest":
        if not isinstance(data, dict):
            raise ValueError("package manifest must be an object")
        allowed = {
            "contract_version", "package_id", "version", "model_family", "industries", "deliverables",
            "required_data", "required_assumptions", "accepted_inputs", "output_artifacts", "output_formats",
            "validation_checks", "execution_capabilities", "adapter_id", "adapter_entry_point",
        }
        if set(data) - allowed:
            raise ValueError("package manifest contains unsupported fields")
        if data.get("contract_version") != "model-package-manifest.v1":
            raise ValueError("unsupported model package manifest contract")
        version = _required_string(data, "version")
        if not _SEMVER.fullmatch(version):
            raise ValueError("package version must use MAJOR.MINOR.PATCH")
        raw_artifacts = data.get("output_artifacts")
        if not isinstance(raw_artifacts, list) or not raw_artifacts:
            raise ValueError("output_artifacts must be a non-empty array")
        artifacts = tuple(ArtifactSpec.from_mapping(item) for item in raw_artifacts)
        if len({item.kind for item in artifacts}) != len(artifacts):
            raise ValueError("output artifact kinds must be unique")
        formats = _strings(data, "output_formats", required=True)
        if set(item.format for item in artifacts) - set(formats):
            raise ValueError("every output artifact format must be declared in output_formats")
        adapter_entry_point = _required_string(data, "adapter_entry_point")
        if not _IDENTIFIER.fullmatch(adapter_entry_point):
            raise ValueError("adapter_entry_point must be an entry-point name")
        return cls(
            contract_version="model-package-manifest.v1", package_id=_required_string(data, "package_id"), version=version,
            model_family=_required_string(data, "model_family"), industries=_strings(data, "industries", required=True),
            deliverables=_strings(data, "deliverables", required=True), required_data=_strings(data, "required_data"),
            required_assumptions=_strings(data, "required_assumptions"), accepted_inputs=_strings(data, "accepted_inputs"),
            output_artifacts=artifacts, output_formats=formats,
            validation_checks=_strings(data, "validation_checks", required=True),
            execution_capabilities=_strings(data, "execution_capabilities", required=True),
            adapter_id=_required_string(data, "adapter_id"), adapter_entry_point=adapter_entry_point,
        )

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.__dict__)
        result["output_artifacts"] = [item.to_dict() for item in self.output_artifacts]
        for key, value in tuple(result.items()):
            if isinstance(value, tuple):
                result[key] = list(value)
        return result


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
    secret_requirements: tuple[str, ...]
    executor_entry_point: str
    packages: tuple[ModelPackageManifest, ...]
    contract_version: str = "provider-manifest.v1"

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ProviderManifest":
        if not isinstance(data, dict) or data.get("contract_version") != "provider-manifest.v1":
            raise ValueError("unsupported provider manifest contract")
        allowed = {
            "contract_version", "provider_id", "version", "execution_mode", "network_required", "license",
            "open_source", "privacy_behavior", "runtime_dependencies", "determinism_level",
            "validation_capabilities", "limitations", "secret_requirements", "executor_entry_point", "packages",
        }
        if set(data) - allowed:
            raise ValueError("provider manifest contains unsupported fields")
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
        executor_entry_point = _required_string(data, "executor_entry_point")
        if not _IDENTIFIER.fullmatch(executor_entry_point):
            raise ValueError("executor_entry_point must be an entry-point name")
        return cls(
            provider_id=provider_id, version=version, execution_mode=mode,
            network_required=data["network_required"], license=_required_string(data, "license"),
            open_source=data["open_source"], privacy_behavior=_strings(data, "privacy_behavior", required=True),
            runtime_dependencies=_strings(data, "runtime_dependencies"),
            determinism_level=_required_string(data, "determinism_level"),
            validation_capabilities=_strings(data, "validation_capabilities", required=True),
            limitations=_strings(data, "limitations"), secret_requirements=_strings(data, "secret_requirements"),
            executor_entry_point=executor_entry_point, packages=packages,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version, "provider_id": self.provider_id,
            "version": self.version, "execution_mode": self.execution_mode,
            "network_required": self.network_required, "license": self.license,
            "open_source": self.open_source, "privacy_behavior": list(self.privacy_behavior),
            "runtime_dependencies": list(self.runtime_dependencies), "determinism_level": self.determinism_level,
            "validation_capabilities": list(self.validation_capabilities), "limitations": list(self.limitations),
            "secret_requirements": list(self.secret_requirements), "executor_entry_point": self.executor_entry_point,
            "packages": [item.to_dict() for item in self.packages],
        }


@dataclass(frozen=True)
class RegisteredPackage:
    provider: ProviderManifest
    package: ModelPackageManifest
    runtime_available: bool
    provider_adapter_available: bool
    provider_executor_available: bool


def _entry_point_names(group: str) -> frozenset[str]:
    return frozenset(item.name for item in metadata.entry_points().select(group=group))


class ProviderRegistry:
    def __init__(
        self,
        providers: Iterable[ProviderManifest],
        *,
        runtime_availability: dict[str, bool] | None = None,
        installed_adapter_entry_points: Iterable[str] | None = None,
        installed_executor_entry_points: Iterable[str] | None = None,
    ) -> None:
        provider_list = tuple(providers)
        if len({item.provider_id for item in provider_list}) != len(provider_list):
            raise ValueError("provider IDs must be unique")
        self._providers = {item.provider_id: item for item in provider_list}
        self._runtime = dict(runtime_availability or {})
        self._adapter_entry_points = frozenset(installed_adapter_entry_points if installed_adapter_entry_points is not None else _entry_point_names("fmr.provider_adapters"))
        self._executor_entry_points = frozenset(installed_executor_entry_points if installed_executor_entry_points is not None else _entry_point_names("fmr.provider_executors"))

    @classmethod
    def discover(
        cls,
        *,
        manifest_directories: Iterable[str | Path] = (),
        disabled_providers: Iterable[str] = (),
        runtime_availability: dict[str, bool] | None = None,
    ) -> "ProviderRegistry":
        disabled = set(disabled_providers)
        documents: list[dict[str, Any]] = []
        root = files("fmr.providers")
        for child in sorted(root.iterdir(), key=lambda item: item.name):
            manifest_file = child.joinpath("manifest.json")
            if child.is_dir() and manifest_file.is_file():
                documents.append(json.loads(manifest_file.read_text(encoding="utf-8")))
        for directory in manifest_directories:
            for manifest_path in sorted(Path(directory).glob("**/manifest.json")):
                documents.append(json.loads(manifest_path.read_text(encoding="utf-8")))
        manifests = [ProviderManifest.from_mapping(item) for item in documents]
        manifests = [item for item in manifests if item.provider_id not in disabled]
        availability = {item.provider_id: all(metadata.packages_distributions().get(name, ()) or _dependency_importable(name) for name in item.runtime_dependencies) for item in manifests}
        availability.update(runtime_availability or {})
        return cls(manifests, runtime_availability=availability)

    builtins = discover

    def providers(self) -> tuple[ProviderManifest, ...]:
        return tuple(self._providers[key] for key in sorted(self._providers))

    def packages(self, family_id: str | None = None) -> tuple[RegisteredPackage, ...]:
        result = []
        for provider in self.providers():
            for package in provider.packages:
                if family_id is None or package.model_family == family_id:
                    result.append(RegisteredPackage(
                        provider, package, self._runtime.get(provider.provider_id, True),
                        package.adapter_entry_point in self._adapter_entry_points,
                        provider.executor_entry_point in self._executor_entry_points,
                    ))
        return tuple(sorted(result, key=lambda item: (item.provider.provider_id, item.package.package_id, item.package.version)))

    def package(self, provider_id: str, package_id: str) -> RegisteredPackage:
        for item in self.packages():
            if item.provider.provider_id == provider_id and item.package.package_id == package_id:
                return item
        raise KeyError((provider_id, package_id))


def _dependency_importable(name: str) -> bool:
    try:
        return metadata.version(name) is not None
    except metadata.PackageNotFoundError:
        return False
