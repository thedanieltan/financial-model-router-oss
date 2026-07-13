"""Deterministic XLSX inspection."""

from fmr.workbook.inspect import inspect_workbook, inspect_workbook_bytes
from fmr.workbook.types import Classification, SheetMap, WorkbookMap

__all__ = [
    "Classification",
    "SheetMap",
    "WorkbookMap",
    "inspect_workbook",
    "inspect_workbook_bytes",
]
