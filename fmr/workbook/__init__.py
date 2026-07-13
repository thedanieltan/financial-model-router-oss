"""Deterministic XLSX inspection, analysis, patch, target and coordinate planning."""

from fmr.workbook.analyse import WorkbookAnalysis, analyse_workbook_map
from fmr.workbook.coordinate_plan import (
    Rectangle,
    plan_workbook_coordinates,
    validate_workbook_coordinate_plan_payload,
)
from fmr.workbook.coordinate_rules import (
    COORDINATE_RULES,
    WorkbookCoordinateRule,
    coordinate_rule_registry_payload,
)
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
    "COORDINATE_RULES",
    "Classification",
    "EvidenceItem",
    "OPERATION_SPECS",
    "OperationTargetResolution",
    "PatchCheck",
    "PatchOperation",
    "Rectangle",
    "ResolutionAnchor",
    "SheetMap",
    "WorkbookAnalysis",
    "WorkbookCoordinateRule",
    "WorkbookEvidence",
    "WorkbookMap",
    "WorkbookOperationSpec",
    "WorkbookPatch",
    "WorkbookTargetResolution",
    "analyse_workbook_map",
    "compile_workbook_patch",
    "coordinate_rule_registry_payload",
    "derive_workbook_evidence",
    "inspect_workbook",
    "inspect_workbook_bytes",
    "operation_spec_registry_payload",
    "plan_workbook_coordinates",
    "resolve_workbook_patch_targets",
    "validate_workbook_coordinate_plan_payload",
    "validate_workbook_patch_payload",
    "validate_workbook_patch_receipt_payload",
    "validate_workbook_target_resolution_payload",
]
