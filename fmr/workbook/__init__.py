"""Deterministic XLSX inspection, analysis, patch planning and target resolution."""

from fmr.workbook.analyse import WorkbookAnalysis, analyse_workbook_map
from fmr.workbook.evidence import EvidenceItem, WorkbookEvidence, derive_workbook_evidence
from fmr.workbook.inspect import inspect_workbook, inspect_workbook_bytes
from fmr.workbook.operation_specs import (
    OPERATION_SPECS,
    WorkbookOperationSpec,
    operation_spec_registry_payload,
)
from fmr.workbook.patch import (
    PatchCheck,
    PatchOperation,
    WorkbookPatch,
    compile_workbook_patch,
)
from fmr.workbook.patch_validation import (
    validate_workbook_patch_payload,
    validate_workbook_patch_receipt_payload,
)
from fmr.workbook.target_resolution import (
    OperationTargetResolution,
    ResolutionAnchor,
    WorkbookTargetResolution,
    resolve_workbook_patch_targets,
    validate_workbook_target_resolution_payload,
)
from fmr.workbook.types import Classification, SheetMap, WorkbookMap

__all__ = [
    "Classification",
    "EvidenceItem",
    "OPERATION_SPECS",
    "OperationTargetResolution",
    "PatchCheck",
    "PatchOperation",
    "ResolutionAnchor",
    "SheetMap",
    "WorkbookAnalysis",
    "WorkbookEvidence",
    "WorkbookMap",
    "WorkbookOperationSpec",
    "WorkbookPatch",
    "WorkbookTargetResolution",
    "analyse_workbook_map",
    "compile_workbook_patch",
    "derive_workbook_evidence",
    "inspect_workbook",
    "inspect_workbook_bytes",
    "operation_spec_registry_payload",
    "resolve_workbook_patch_targets",
    "validate_workbook_patch_payload",
    "validate_workbook_patch_receipt_payload",
    "validate_workbook_target_resolution_payload",
]
