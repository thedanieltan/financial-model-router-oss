from __future__ import annotations

import re
from typing import Any

from fmr.registry import ProviderManifest


def validate_version_transition(current: dict[str, Any], previous: dict[str, Any]) -> tuple[str, ...]:
    """Validate monotonic versions and require major bumps for breaking changes."""

    try:
        new = ProviderManifest.from_mapping(current)
        old = ProviderManifest.from_mapping(previous)
    except ValueError as exc:
        return (str(exc),)
    issues: list[str] = []
    if new.provider_id != old.provider_id:
        issues.append("provider_id cannot change across a version transition")
        return tuple(issues)
    new_version = _parts(new.version)
    old_version = _parts(old.version)
    if new_version <= old_version:
        issues.append("provider version must increase")
    old_packages = {item.package_id: item for item in old.packages}
    new_packages = {item.package_id: item for item in new.packages}
    removed = sorted(set(old_packages) - set(new_packages))
    provider_breaking = bool(removed) or new.execution_mode != old.execution_mode or new.executor_entry_point != old.executor_entry_point
    if provider_breaking and new_version[0] <= old_version[0]:
        issues.append("removing packages or changing execution mode/executor requires a provider major-version bump")
    for package_id in sorted(set(old_packages) & set(new_packages)):
        before = old_packages[package_id]
        after = new_packages[package_id]
        before_version = _parts(before.version)
        after_version = _parts(after.version)
        if after_version < before_version:
            issues.append(f"package version cannot decrease: {package_id}")
        breaking = (
            after.model_family != before.model_family
            or after.adapter_entry_point != before.adapter_entry_point
            or not set(before.deliverables).issubset(after.deliverables)
            or not set(before.output_artifacts).issubset(after.output_artifacts)
            or not set(after.required_data).issubset(before.required_data)
            or not set(after.required_assumptions).issubset(before.required_assumptions)
        )
        if breaking and after_version[0] <= before_version[0]:
            issues.append(f"breaking package contract change requires a major-version bump: {package_id}")
    return tuple(issues)


def _parts(version: str) -> tuple[int, int, int, int, str, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:([a-z]+)(\d+))?", version)
    if match is None:
        raise ValueError("version is invalid")
    major, minor, patch, label, sequence = match.groups()
    return (
        int(major), int(minor), int(patch),
        1 if label is None else 0,
        label or "",
        int(sequence or 0),
    )
