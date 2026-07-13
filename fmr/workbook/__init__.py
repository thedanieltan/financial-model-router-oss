"""Deterministic XLSX inspection, analysis and patch planning."""

from fmr.workbook.analyse import WorkbookAnalysis, analyse_workbook_map
from fmr.workbook.evidence import EvidenceItem, WorkbookEvidence, derive_workbook_evidence
from fmr.workbook.inspect import inspect_workbook, inspect_workbook_bytes
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
from fmr.workbook.types import Classification, SheetMap, WorkbookMap

__all__ = [
    "Classification",
    "EvidenceItem",
    "PatchCheck",
    "PatchOperation",
    "SheetMap",
    "WorkbookAnalysis",
    "WorkbookEvidence",
    "WorkbookMap",
    "WorkbookPatch",
    "analyse_workbook_map",
    "compile_workbook_patch",
    "derive_workbook_evidence",
    "inspect_workbook",
    "inspect_workbook_bytes",
    "validate_workbook_patch_payload",
    "validate_workbook_patch_receipt_payload",
]
