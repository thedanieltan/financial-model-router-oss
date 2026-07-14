from __future__ import annotations

import hashlib
import json
import re
import tomllib
import zipfile
from pathlib import Path
from typing import Any

from fmr.core.families import FAMILY_BY_ID
from fmr.registry import ProviderManifest
from fmr.sdk.versioning import validate_version_transition

_NAME = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_TARGET = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*$")


def initialize_provider_project(destination: str | Path, provider_id: str, *, force: bool = False) -> tuple[Path, ...]:
    """Create a small, executable handoff-only provider project."""

    if not _NAME.fullmatch(provider_id):
        raise ValueError("provider_id must be lowercase kebab-case")
    root = Path(destination)
    if root.exists() and any(root.iterdir()) and not force:
        raise ValueError("destination is not empty")
    package = provider_id.replace("-", "_")
    files = {
        "pyproject.toml": _pyproject(provider_id, package),
        "manifest.json": json.dumps(_manifest(provider_id), indent=2, sort_keys=True) + "\n",
        "fixtures/model-job.v2.json": json.dumps(_fixture(), indent=2, sort_keys=True) + "\n",
        f"src/{package}/__init__.py": "\"\"\"FMR provider plugin.\"\"\"\n",
        f"src/{package}/plugin.py": _plugin(provider_id),
        "README.md": _readme(provider_id),
    }
    created: list[Path] = []
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not force:
            raise ValueError(f"refusing to overwrite {relative}")
        target.write_text(content, encoding="utf-8")
        created.append(target)
    return tuple(created)


def validate_provider_project(
    root: str | Path,
    *,
    previous_manifest: str | Path | None = None,
) -> dict[str, Any]:
    """Validate project metadata without importing provider implementation code."""

    project_root = Path(root)
    checks: list[dict[str, Any]] = []
    try:
        manifest_payload = json.loads((project_root / "manifest.json").read_text(encoding="utf-8"))
        manifest = ProviderManifest.from_mapping(manifest_payload)
        checks.append(_check("manifest_contract", True))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return _project_result(None, [_check("manifest_contract", False, reason=str(exc))])
    unknown = sorted({package.model_family for package in manifest.packages if package.model_family not in FAMILY_BY_ID})
    checks.append(_check("registered_model_families", not unknown, unknown_families=unknown))
    try:
        metadata = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
        entry_points = metadata["project"]["entry-points"]
        adapters = entry_points.get("fmr.provider_adapters", {})
        executors = entry_points.get("fmr.provider_executors", {})
        if not isinstance(adapters, dict) or not isinstance(executors, dict):
            raise ValueError("provider entry-point groups must be TOML tables")
        missing_adapters = sorted({item.adapter_entry_point for item in manifest.packages} - set(adapters))
        missing_executors = [] if manifest.executor_entry_point in executors else [manifest.executor_entry_point]
        checks.append(_check("declared_adapter_entry_points", not missing_adapters, missing=missing_adapters))
        checks.append(_check("declared_executor_entry_point", not missing_executors, missing=missing_executors))
        invalid_targets = sorted(name for name, target in {**adapters, **executors}.items() if not isinstance(target, str) or not _TARGET.fullmatch(target))
        checks.append(_check("entry_point_targets", not invalid_targets, invalid=invalid_targets))
        project_version = metadata["project"].get("version")
        checks.append(_check("project_version", project_version == manifest.version, manifest_version=manifest.version, project_version=project_version))
    except (OSError, KeyError, ValueError, tomllib.TOMLDecodeError) as exc:
        checks.append(_check("project_metadata", False, reason=str(exc)))
    if previous_manifest is not None:
        try:
            previous = json.loads(Path(previous_manifest).read_text(encoding="utf-8"))
            issues = list(validate_version_transition(manifest_payload, previous))
        except (OSError, json.JSONDecodeError) as exc:
            issues = [str(exc)]
        checks.append(_check("version_transition", not issues, issues=issues))
    return _project_result(manifest.provider_id, checks)


def build_provider_bundle(root: str | Path, destination: str | Path) -> dict[str, Any]:
    """Create a deterministic, hash-pinned provider submission bundle."""

    project_root = Path(root).resolve()
    validation = validate_provider_project(project_root)
    if validation["status"] != "passed":
        raise ValueError("provider project validation failed")
    provider_id = validation["provider_id"]
    target_root = Path(destination)
    target_root.mkdir(parents=True, exist_ok=True)
    output = target_root / f"{provider_id}-provider.zip"
    if output.exists():
        raise ValueError("provider bundle already exists")
    members = sorted(
        path for path in project_root.rglob("*")
        if path.is_file() and _bundle_member(path.relative_to(project_root))
    )
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in members:
            info = zipfile.ZipInfo(path.relative_to(project_root).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    payload = output.read_bytes()
    return {
        "contract_version": "provider-sdk-package-result.v1",
        "provider_id": provider_id,
        "path": str(output),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
        "member_count": len(members),
    }


def _check(name: str, passed: bool, **details: Any) -> dict[str, Any]:
    return {"check": name, "status": "passed" if passed else "failed", "details": details}


def _project_result(provider_id: str | None, checks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "contract_version": "provider-sdk-validation-result.v1",
        "status": "passed" if checks and all(item["status"] == "passed" for item in checks) else "failed",
        "provider_id": provider_id,
        "checks": checks,
    }


def _bundle_member(relative: Path) -> bool:
    excluded = {".git", ".venv", "__pycache__", "build", "dist"}
    return not any(part in excluded or part.endswith(".egg-info") for part in relative.parts)


def _manifest(provider_id: str) -> dict[str, Any]:
    entry_point = f"{provider_id}-handoff"
    return {
        "contract_version": "provider-manifest.v1",
        "provider_id": provider_id,
        "version": "0.1.0",
        "execution_mode": "handoff_only",
        "network_required": False,
        "license": "Apache-2.0",
        "open_source": True,
        "privacy_behavior": ["payload_written_to_managed_local_artifact"],
        "runtime_dependencies": [],
        "determinism_level": "deterministic",
        "validation_capabilities": ["artifact_hash"],
        "limitations": ["example_handoff_only_provider"],
        "secret_requirements": [],
        "executor_entry_point": entry_point,
        "packages": [{
            "contract_version": "model-package-manifest.v1",
            "package_id": f"{provider_id}/operating-company-dcf-handoff",
            "version": "0.1.0",
            "model_family": "operating_company_dcf",
            "industries": ["generic"],
            "deliverables": ["external_provider_handoff"],
            "required_data": [],
            "required_assumptions": [],
            "accepted_inputs": ["model-job.v2"],
            "output_artifacts": [{"kind": "external_provider_handoff", "format": "json", "required": True}],
            "output_formats": ["json"],
            "validation_checks": ["artifact_hash"],
            "execution_capabilities": ["handoff_only"],
            "adapter_id": f"{provider_id}-adapter-v1",
            "adapter_entry_point": entry_point,
        }],
    }


def _fixture() -> dict[str, Any]:
    return {
        "contract_version": "model-job.v2",
        "objective": "Prepare an external operating-company DCF handoff",
        "model_family": "operating_company_dcf",
        "requested_deliverables": ["external_provider_handoff"],
        "available_data": [],
        "available_assumptions": [],
        "input_references": {},
        "output_formats": ["json"],
    }


def _pyproject(provider_id: str, package: str) -> str:
    entry_point = f"{provider_id}-handoff"
    return f'''[build-system]\nrequires = ["setuptools>=70"]\nbuild-backend = "setuptools.build_meta"\n\n[project]\nname = "fmr-provider-{provider_id}"\nversion = "0.1.0"\nrequires-python = ">=3.11"\ndependencies = ["financial-model-router>=1.0.0a1,<2"]\n\n[project.entry-points."fmr.provider_adapters"]\n{entry_point} = "{package}.plugin:Adapter"\n\n[project.entry-points."fmr.provider_executors"]\n{entry_point} = "{package}.plugin:Executor"\n\n[tool.setuptools.packages.find]\nwhere = ["src"]\n'''


def _plugin(provider_id: str) -> str:
    return f'''from __future__ import annotations\n\nimport hashlib\nimport json\nfrom pathlib import Path\nfrom typing import Any\n\nfrom fmr.core.jobs import ModelJob\nfrom fmr.registry import RegisteredPackage\n\n\nclass Adapter:\n    def compile(self, job: ModelJob, registered: RegisteredPackage) -> dict[str, Any]:\n        return {{"adapter_id": registered.package.adapter_id, "external_request": job.to_dict()}}\n\n\nclass Executor:\n    def execute(self, handoff: dict[str, Any], output_dir: Path, secrets: dict[str, str]) -> dict[str, Any]:\n        if secrets:\n            raise ValueError("this provider does not accept secrets")\n        output_dir.mkdir(parents=True, exist_ok=True)\n        output = output_dir / "external-provider-handoff.json"\n        if output.exists():\n            raise ValueError("output path already exists")\n        data = (json.dumps(handoff["provider_payload"], indent=2, sort_keys=True) + "\\n").encode()\n        output.write_bytes(data)\n        return {{\n            "provider_receipt_version": "{provider_id}-receipt.v1",\n            "status": "completed",\n            "handoff_sha256": handoff["handoff_sha256"],\n            "output_artifacts": [{{\n                "kind": "external_provider_handoff", "format": "json", "path": str(output),\n                "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data),\n            }}],\n            "validation": {{"status": "passed", "checks": ["artifact_hash"]}},\n        }}\n'''


def _readme(provider_id: str) -> str:
    return f'''# {provider_id}\n\nGenerated FMR handoff-only provider example.\n\n```bash\npip install -e .\nfmr-provider validate .\nfmr-provider test .\nfmr-provider package . --destination dist\n```\n'''
