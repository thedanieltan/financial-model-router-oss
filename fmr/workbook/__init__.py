"""Deterministic XLSX inspection and workbook analysis."""

from fmr.workbook.analyse import WorkbookAnalysis, analyse_workbook_map
from fmr.workbook.evidence import EvidenceItem, WorkbookEvidence, derive_workbook_evidence
from fmr.workbook.inspect import inspect_workbook, inspect_workbook_bytes
from fmr.workbook.types import Classification, SheetMap, WorkbookMap

__all__ = [
    "Classification",
    "EvidenceItem",
    "SheetMap",
    "WorkbookAnalysis",
    "WorkbookEvidence",
    "WorkbookMap",
    "analyse_workbook_map",
    "derive_workbook_evidence",
    "inspect_workbook",
    "inspect_workbook_bytes",
]
