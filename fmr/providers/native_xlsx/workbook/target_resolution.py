from __future__ import annotations

import hashlib
import json
import re
import string
from dataclasses import dataclass
from typing import Any

from fmr.providers.native_xlsx.workbook.analyse import WorkbookAnalysis
from fmr.providers.native_xlsx.workbook.classify import normalise_label
from fmr.providers.native_xlsx.workbook.operation_specs import (
    OPERATION_SPECS,
    WorkbookOperationSpec,
    operation_spec_registry_payload,
)
from fmr.providers.native_xlsx.workbook.patch import (
    compile_workbook_patch,
    validate_workbook_patch_payload,
)
from fmr.providers.native_xlsx.workbook.types import SheetMap, WorkbookMap

_RESOLUTION_ID_RE = re.compile(r"^fmrr_[0-9a-f]{24}$")
_ALLOWED_STATUSES = {
    "resolved_existing",
    "resolved_new",
    "resolved_planned",
    "resolved_set",
    "blocked",
}
_ALLOWED_CONFIDENCE = {"none", "medium", "high"}
_ALLOWED_CONTROLS = {
    "executor_not_included",
    "no_cell_coordinates",
    "no_formula_generation",
    "operation_specs_pinned",
    "patch_digest_pinned",
    "source_hash_pinned",
    "target_resolution_only",
}
_FORBIDDEN_KEYS = {
    "cell",
    "cell_address",
    "cell_write",
    "formula",
    "macro",
    "script",
    "vba",
    "workbook_bytes",
}


@dataclass(frozen=True)
class ResolutionAnchor:
    sheet_name: str
    position: int
    visibility: str
    used_range: str | None
    candidate_role: str
    role_confidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheet_name": self.sheet_name,
            "position": self.position,
            "visibility": self.visibility,
            "used_range": self.used_range,
            "candidate_role": self.candidate_role,
            "role_confidence": self.role_confidence,
        }


@dataclass(frozen=True)
class OperationTargetResolution:
    sequence: int
    operation_id: str
    source_operation: str
    specification_ref: str
    semantic_role: str
    status: str
    confidence: str
    target_scope: str
    sheet_names: tuple[str, ...]
    canonical_sheet_name: str | None
    placement: str
    anchors: tuple[ResolutionAnchor, ...]
    evidence: tuple[str, ...]
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "operation_id": self.operation_id,
            "source_operation": self.source_operation,
            "specification_ref": self.specification_ref,
            "semantic_role": self.semantic_role,
            "status": self.status,
            "confidence": self.confidence,
            "target": {
                "scope": self.target_scope,
                "sheet_names": list(self.sheet_names),
                "canonical_sheet_name": self.canonical_sheet_name,
                "placement": self.placement,
                "anchors": [anchor.to_dict() for anchor in self.anchors],
            },
            "evidence": list(self.evidence),
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class WorkbookTargetResolution:
    resolution_id: str
    patch_id: str
    patch_sha256: str
    operation_specs_sha256: str
    source_filename: str
    source_sha256: str
    source_size_bytes: int
    ready_for_executor: bool
    execution_supported_by_this_release: bool
    blockers: tuple[str, ...]
    resolutions: tuple[OperationTargetResolution, ...]
    controls: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": "workbook-target-resolution.v1",
            "resolution_id": self.resolution_id,
            "patch_id": self.patch_id,
            "patch_sha256": self.patch_sha256,
            "operation_specs_sha256": self.operation_specs_sha256,
            "source": {
                "filename": self.source_filename,
                "sha256": self.source_sha256,
                "size_bytes": self.source_size_bytes,
            },
            "ready_for_executor": self.ready_for_executor,
            "execution_supported_by_this_release": (
                self.execution_supported_by_this_release
            ),
            "blockers": list(self.blockers),
            "resolutions": [item.to_dict() for item in self.resolutions],
            "controls": list(self.controls),
        }


def resolve_workbook_patch_targets(
    analysis: WorkbookAnalysis,
    patch: dict[str, Any],
) -> WorkbookTargetResolution:
    patch_issues = validate_workbook_patch_payload(patch)
    if patch_issues:
        raise ValueError(f"invalid workbook patch: {'; '.join(patch_issues)}")
    expected_patch = compile_workbook_patch(analysis).to_dict()
    if patch != expected_patch:
        raise ValueError("workbook patch does not match deterministic recompilation")

    registry = operation_spec_registry_payload()
    resolutions: list[OperationTargetResolution] = []
    blockers: list[str] = []
    planned_sheets: dict[str, str] = {}

    if not patch["ready_for_executor"]:
        blockers.extend(f"patch:{item}" for item in patch["blockers"])

    for operation in patch["operations"]:
        source_operation = operation["source_operation"]
        spec = OPERATION_SPECS[source_operation]
        resolution = _resolve_operation(
            operation,
            spec,
            analysis.workbook_map,
            planned_sheets,
        )
        resolutions.append(resolution)
        if (
            resolution.status == "resolved_new"
            and resolution.canonical_sheet_name is not None
        ):
            planned_sheets[
                normalise_label(resolution.canonical_sheet_name)
            ] = resolution.operation_id
        blockers.extend(
            f"{resolution.operation_id}:{item}" for item in resolution.blockers
        )

    if not resolutions:
        blockers.append("no_target_resolutions")

    deduplicated_blockers = tuple(dict.fromkeys(blockers))
    patch_sha256 = _digest(patch)
    controls = tuple(sorted(_ALLOWED_CONTROLS))
    provisional = {
        "contract_version": "workbook-target-resolution.v1",
        "patch_id": patch["patch_id"],
        "patch_sha256": patch_sha256,
        "operation_specs_sha256": registry["registry_sha256"],
        "source": dict(patch["source"]),
        "ready_for_executor": not deduplicated_blockers,
        "execution_supported_by_this_release": False,
        "blockers": list(deduplicated_blockers),
        "resolutions": [item.to_dict() for item in resolutions],
        "controls": list(controls),
    }
    resolution_id = f"fmrr_{_digest(provisional)[:24]}"
    return WorkbookTargetResolution(
        resolution_id=resolution_id,
        patch_id=patch["patch_id"],
        patch_sha256=patch_sha256,
        operation_specs_sha256=registry["registry_sha256"],
        source_filename=patch["source"]["filename"],
        source_sha256=patch["source"]["sha256"],
        source_size_bytes=patch["source"]["size_bytes"],
        ready_for_executor=not deduplicated_blockers,
        execution_supported_by_this_release=False,
        blockers=deduplicated_blockers,
        resolutions=tuple(resolutions),
        controls=controls,
    )


def validate_workbook_target_resolution_payload(
    payload: Any,
    *,
    analysis: WorkbookAnalysis | None = None,
    patch: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ("target resolution must be an object",)
    _reject_extra_keys(
        payload,
        {
            "contract_version",
            "resolution_id",
            "patch_id",
            "patch_sha256",
            "operation_specs_sha256",
            "source",
            "ready_for_executor",
            "execution_supported_by_this_release",
            "blockers",
            "resolutions",
            "controls",
        },
        "target resolution",
        issues,
    )
    if payload.get("contract_version") != "workbook-target-resolution.v1":
        issues.append("unsupported contract_version")
    if _contains_forbidden_key(payload):
        issues.append("target resolution contains executable workbook fields")

    resolution_id = payload.get("resolution_id")
    if not isinstance(resolution_id, str) or not _RESOLUTION_ID_RE.fullmatch(
        resolution_id
    ):
        issues.append("resolution_id is invalid")
    patch_id = payload.get("patch_id")
    if not isinstance(patch_id, str) or not re.fullmatch(
        r"fmrp_[0-9a-f]{24}", patch_id
    ):
        issues.append("patch_id is invalid")
    for field in ("patch_sha256", "operation_specs_sha256"):
        if not _is_sha256(payload.get(field)):
            issues.append(f"{field} must be a SHA-256 hex string")

    source = payload.get("source")
    if not isinstance(source, dict):
        issues.append("source must be an object")
    else:
        _reject_extra_keys(
            source,
            {"filename", "sha256", "size_bytes"},
            "source",
            issues,
        )
        if not isinstance(source.get("filename"), str) or not source.get(
            "filename"
        ):
            issues.append("source.filename must be a non-empty string")
        if not _is_sha256(source.get("sha256")):
            issues.append("source.sha256 must be a SHA-256 hex string")
        if not isinstance(source.get("size_bytes"), int) or source.get(
            "size_bytes"
        ) < 0:
            issues.append("source.size_bytes must be a non-negative integer")

    for field in ("ready_for_executor", "execution_supported_by_this_release"):
        if not isinstance(payload.get(field), bool):
            issues.append(f"{field} must be boolean")
    if payload.get("execution_supported_by_this_release") is not False:
        issues.append(
            "execution_supported_by_this_release must be false for this release"
        )
    blockers = payload.get("blockers")
    if not _is_string_list(blockers):
        issues.append("blockers must be an array of strings")
    elif payload.get("ready_for_executor") is not (len(blockers) == 0):
        issues.append("ready_for_executor does not match blockers")

    resolutions = payload.get("resolutions")
    if not isinstance(resolutions, list) or not resolutions:
        issues.append("resolutions must be a non-empty array")
    else:
        for index, item in enumerate(resolutions):
            path = f"resolutions[{index}]"
            if not isinstance(item, dict):
                issues.append(f"{path} must be an object")
                continue
            _validate_resolution_item(item, index, path, issues)

    controls = payload.get("controls")
    if not _is_string_list(controls):
        issues.append("controls must be an array of strings")
    elif set(controls) != _ALLOWED_CONTROLS or len(controls) != len(
        _ALLOWED_CONTROLS
    ):
        issues.append("controls do not match required target-resolution controls")

    registry_sha = operation_spec_registry_payload()["registry_sha256"]
    if payload.get("operation_specs_sha256") != registry_sha:
        issues.append("operation_specs_sha256 does not match registry")

    if isinstance(resolution_id, str) and _RESOLUTION_ID_RE.fullmatch(
        resolution_id
    ):
        candidate = dict(payload)
        candidate.pop("resolution_id", None)
        expected_id = f"fmrr_{_digest(candidate)[:24]}"
        if resolution_id != expected_id:
            issues.append("resolution_id does not match payload")

    if (analysis is None) is not (patch is None):
        issues.append("analysis and patch must be supplied together")
    elif analysis is not None and patch is not None:
        try:
            expected = resolve_workbook_patch_targets(analysis, patch).to_dict()
        except ValueError as exc:
            issues.append(f"cannot recompute target resolution: {exc}")
        else:
            if payload != expected:
                issues.append(
                    "target resolution does not match deterministic recomputation"
                )

    return tuple(dict.fromkeys(issues))


def _resolve_operation(
    operation: dict[str, Any],
    spec: WorkbookOperationSpec,
    workbook_map: WorkbookMap,
    planned_sheets: dict[str, str],
) -> OperationTargetResolution:
    if spec.cardinality == "required_roles":
        return _resolve_required_roles(operation, spec, workbook_map)
    if spec.cardinality == "many":
        return _resolve_many(operation, spec, workbook_map)
    return _resolve_one_or_create(
        operation,
        spec,
        workbook_map,
        planned_sheets,
    )


def _resolve_required_roles(
    operation: dict[str, Any],
    spec: WorkbookOperationSpec,
    workbook_map: WorkbookMap,
) -> OperationTargetResolution:
    anchors: list[ResolutionAnchor] = []
    evidence: list[str] = []
    blockers: list[str] = []
    confidence = "high"
    for role in spec.required_sheet_roles:
        matches = [
            sheet
            for sheet in workbook_map.sheets
            if sheet.candidate_role.value == role
            and sheet.candidate_role.confidence in {"medium", "high"}
        ]
        if not matches:
            blockers.append(f"missing_required_sheet_role:{role}")
            continue
        if len(matches) > 1:
            blockers.append(
                f"ambiguous_required_sheet_role:{role}:"
                + ",".join(sheet.name for sheet in matches)
            )
            continue
        sheet = matches[0]
        anchors.append(_anchor(sheet))
        evidence.append(
            f"required_role:{role}:sheet:{sheet.name}:"
            f"{sheet.candidate_role.confidence}"
        )
        if sheet.candidate_role.confidence == "medium":
            confidence = "medium"
    return _resolution(
        operation,
        spec,
        status="blocked" if blockers else "resolved_set",
        confidence="none" if blockers else confidence,
        sheet_names=tuple(anchor.sheet_name for anchor in anchors),
        canonical_sheet_name=None,
        anchors=tuple(anchors),
        evidence=tuple(evidence),
        blockers=tuple(blockers),
    )


def _resolve_many(
    operation: dict[str, Any],
    spec: WorkbookOperationSpec,
    workbook_map: WorkbookMap,
) -> OperationTargetResolution:
    matches: list[tuple[int, SheetMap, tuple[str, ...]]] = []
    for sheet in workbook_map.sheets:
        rank, evidence = _candidate_rank(sheet, spec)
        if rank >= 2:
            matches.append((rank, sheet, evidence))
    matches.sort(key=lambda item: item[1].position)
    if not matches:
        return _resolution(
            operation,
            spec,
            status="blocked",
            confidence="none",
            sheet_names=(),
            canonical_sheet_name=None,
            anchors=(),
            evidence=(),
            blockers=(f"no_existing_target:{spec.semantic_role}",),
        )
    confidence = "high" if all(rank == 3 for rank, _, _ in matches) else "medium"
    anchors = tuple(_anchor(sheet) for _, sheet, _ in matches)
    evidence = tuple(
        message
        for _, sheet, messages in matches
        for message in (f"sheet:{sheet.name}", *messages)
    )
    return _resolution(
        operation,
        spec,
        status="resolved_set",
        confidence=confidence,
        sheet_names=tuple(anchor.sheet_name for anchor in anchors),
        canonical_sheet_name=None,
        anchors=anchors,
        evidence=evidence,
        blockers=(),
    )


def _resolve_one_or_create(
    operation: dict[str, Any],
    spec: WorkbookOperationSpec,
    workbook_map: WorkbookMap,
    planned_sheets: dict[str, str],
) -> OperationTargetResolution:
    matches: list[tuple[int, SheetMap, tuple[str, ...]]] = []
    for sheet in workbook_map.sheets:
        rank, evidence = _candidate_rank(sheet, spec)
        if rank >= 2:
            matches.append((rank, sheet, evidence))
    if matches:
        highest = max(rank for rank, _, _ in matches)
        top = [item for item in matches if item[0] == highest]
        top.sort(key=lambda item: item[1].position)
        if len(top) > 1:
            names = ",".join(sheet.name for _, sheet, _ in top)
            return _resolution(
                operation,
                spec,
                status="blocked",
                confidence="none",
                sheet_names=tuple(sheet.name for _, sheet, _ in top),
                canonical_sheet_name=spec.canonical_sheet_name,
                anchors=tuple(_anchor(sheet) for _, sheet, _ in top),
                evidence=tuple(
                    message
                    for _, sheet, messages in top
                    for message in (f"sheet:{sheet.name}", *messages)
                ),
                blockers=(f"ambiguous_target:{spec.semantic_role}:{names}",),
            )
        rank, sheet, evidence = top[0]
        return _resolution(
            operation,
            spec,
            status="resolved_existing",
            confidence="high" if rank == 3 else "medium",
            sheet_names=(sheet.name,),
            canonical_sheet_name=spec.canonical_sheet_name,
            anchors=(_anchor(sheet),),
            evidence=(f"sheet:{sheet.name}", *evidence),
            blockers=(),
        )
    if spec.create_if_missing and spec.canonical_sheet_name:
        planned_by = planned_sheets.get(
            normalise_label(spec.canonical_sheet_name)
        )
        if planned_by is not None:
            return _resolution(
                operation,
                spec,
                status="resolved_planned",
                confidence="high",
                sheet_names=(spec.canonical_sheet_name,),
                canonical_sheet_name=spec.canonical_sheet_name,
                anchors=(),
                evidence=(
                    f"planned_sheet:{spec.canonical_sheet_name}",
                    f"planned_by_operation:{planned_by}",
                ),
                blockers=(),
            )
        return _resolution(
            operation,
            spec,
            status="resolved_new",
            confidence="high",
            sheet_names=(spec.canonical_sheet_name,),
            canonical_sheet_name=spec.canonical_sheet_name,
            anchors=(),
            evidence=(
                f"no_existing_match:{spec.semantic_role}",
                f"canonical_sheet_name:{spec.canonical_sheet_name}",
            ),
            blockers=(),
        )
    return _resolution(
        operation,
        spec,
        status="blocked",
        confidence="none",
        sheet_names=(),
        canonical_sheet_name=spec.canonical_sheet_name,
        anchors=(),
        evidence=(),
        blockers=(f"no_existing_target:{spec.semantic_role}",),
    )


def _candidate_rank(
    sheet: SheetMap,
    spec: WorkbookOperationSpec,
) -> tuple[int, tuple[str, ...]]:
    rank = 0
    evidence: list[str] = []
    normalised_name = normalise_label(sheet.name)
    aliases = tuple(normalise_label(alias) for alias in spec.name_aliases)
    exact_aliases = [alias for alias in aliases if normalised_name == alias]
    partial_aliases = [
        alias
        for alias in aliases
        if alias and alias in normalised_name and alias not in exact_aliases
    ]
    if exact_aliases:
        rank = 3
        evidence.append(f"exact_name_alias:{exact_aliases[0]}")
    elif partial_aliases:
        rank = max(rank, 2)
        evidence.append(f"name_alias:{partial_aliases[0]}")

    if (
        sheet.candidate_role.value in spec.accepted_sheet_roles
        and sheet.candidate_role.confidence in {"medium", "high"}
    ):
        role_rank = 3 if sheet.candidate_role.confidence == "high" else 2
        rank = max(rank, role_rank)
        evidence.append(
            f"candidate_role:{sheet.candidate_role.value}:"
            f"{sheet.candidate_role.confidence}"
        )

    metric_matches = sorted(
        set(sheet.candidate_metrics).intersection(spec.metric_hints)
    )
    if len(metric_matches) >= 2:
        rank = max(rank, 2)
    if metric_matches:
        evidence.append(f"metric_hints:{','.join(metric_matches)}")
    return rank, tuple(evidence)


def _resolution(
    operation: dict[str, Any],
    spec: WorkbookOperationSpec,
    *,
    status: str,
    confidence: str,
    sheet_names: tuple[str, ...],
    canonical_sheet_name: str | None,
    anchors: tuple[ResolutionAnchor, ...],
    evidence: tuple[str, ...],
    blockers: tuple[str, ...],
) -> OperationTargetResolution:
    return OperationTargetResolution(
        sequence=operation["sequence"],
        operation_id=operation["operation_id"],
        source_operation=operation["source_operation"],
        specification_ref=spec.specification_ref,
        semantic_role=spec.semantic_role,
        status=status,
        confidence=confidence,
        target_scope=spec.target_scope,
        sheet_names=sheet_names,
        canonical_sheet_name=canonical_sheet_name,
        placement=spec.placement,
        anchors=anchors,
        evidence=evidence,
        blockers=blockers,
    )


def _anchor(sheet: SheetMap) -> ResolutionAnchor:
    return ResolutionAnchor(
        sheet_name=sheet.name,
        position=sheet.position,
        visibility=sheet.visibility,
        used_range=sheet.used_range,
        candidate_role=sheet.candidate_role.value,
        role_confidence=sheet.candidate_role.confidence,
    )


def _validate_resolution_item(
    item: dict[str, Any],
    index: int,
    path: str,
    issues: list[str],
) -> None:
    _reject_extra_keys(
        item,
        {
            "sequence",
            "operation_id",
            "source_operation",
            "specification_ref",
            "semantic_role",
            "status",
            "confidence",
            "target",
            "evidence",
            "blockers",
        },
        path,
        issues,
    )
    expected_sequence = index + 1
    if item.get("sequence") != expected_sequence:
        issues.append(f"{path}.sequence must equal {expected_sequence}")
    if item.get("operation_id") != f"op-{expected_sequence:03d}":
        issues.append(f"{path}.operation_id is invalid")
    source_operation = item.get("source_operation")
    spec = OPERATION_SPECS.get(source_operation)
    if spec is None:
        issues.append(f"{path}.source_operation is not approved")
    else:
        if item.get("specification_ref") != spec.specification_ref:
            issues.append(f"{path}.specification_ref is invalid")
        if item.get("semantic_role") != spec.semantic_role:
            issues.append(f"{path}.semantic_role is invalid")
    if item.get("status") not in _ALLOWED_STATUSES:
        issues.append(f"{path}.status is invalid")
    if item.get("confidence") not in _ALLOWED_CONFIDENCE:
        issues.append(f"{path}.confidence is invalid")
    evidence = item.get("evidence")
    blockers = item.get("blockers")
    if not _is_string_list(evidence):
        issues.append(f"{path}.evidence must be an array of strings")
    if not _is_string_list(blockers):
        issues.append(f"{path}.blockers must be an array of strings")
    elif (item.get("status") == "blocked") is not (len(blockers) > 0):
        issues.append(f"{path}.status does not match blockers")

    target = item.get("target")
    if not isinstance(target, dict):
        issues.append(f"{path}.target must be an object")
        return
    _reject_extra_keys(
        target,
        {
            "scope",
            "sheet_names",
            "canonical_sheet_name",
            "placement",
            "anchors",
        },
        f"{path}.target",
        issues,
    )
    if spec is not None:
        if target.get("scope") != spec.target_scope:
            issues.append(f"{path}.target.scope is invalid")
        if target.get("placement") != spec.placement:
            issues.append(f"{path}.target.placement is invalid")
        if target.get("canonical_sheet_name") != spec.canonical_sheet_name:
            issues.append(f"{path}.target.canonical_sheet_name is invalid")
    if not _is_string_list(target.get("sheet_names")):
        issues.append(f"{path}.target.sheet_names must be an array of strings")
    anchors = target.get("anchors")
    if not isinstance(anchors, list):
        issues.append(f"{path}.target.anchors must be an array")
    else:
        for anchor_index, anchor in enumerate(anchors):
            _validate_anchor(
                anchor,
                f"{path}.target.anchors[{anchor_index}]",
                issues,
            )


def _validate_anchor(
    anchor: Any,
    path: str,
    issues: list[str],
) -> None:
    if not isinstance(anchor, dict):
        issues.append(f"{path} must be an object")
        return
    _reject_extra_keys(
        anchor,
        {
            "sheet_name",
            "position",
            "visibility",
            "used_range",
            "candidate_role",
            "role_confidence",
        },
        path,
        issues,
    )
    if not isinstance(anchor.get("sheet_name"), str) or not anchor.get(
        "sheet_name"
    ):
        issues.append(f"{path}.sheet_name must be a non-empty string")
    if not isinstance(anchor.get("position"), int) or anchor.get("position") < 1:
        issues.append(f"{path}.position must be a positive integer")
    if anchor.get("visibility") not in {"visible", "hidden", "veryHidden"}:
        issues.append(f"{path}.visibility is invalid")
    if anchor.get("used_range") is not None and not isinstance(
        anchor.get("used_range"), str
    ):
        issues.append(f"{path}.used_range must be a string or null")
    if not isinstance(anchor.get("candidate_role"), str) or not anchor.get(
        "candidate_role"
    ):
        issues.append(f"{path}.candidate_role must be a non-empty string")
    if anchor.get("role_confidence") not in {"low", "medium", "high"}:
        issues.append(f"{path}.role_confidence is invalid")


def _reject_extra_keys(
    payload: dict[str, Any],
    allowed: set[str],
    path: str,
    issues: list[str],
) -> None:
    extras = sorted(set(payload).difference(allowed))
    if extras:
        issues.append(f"{path} contains unsupported fields: {','.join(extras)}")


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                return True
            if _contains_forbidden_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in string.hexdigits for character in value)
    )


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and bool(item) for item in value
    )


def _digest(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()
