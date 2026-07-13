"""Financial Model Router public API."""

from fmr.plan import build_plan
from fmr.router import route_request
from fmr.workbook import (
    analyse_workbook_map,
    compile_workbook_patch,
    derive_workbook_evidence,
    inspect_workbook,
    inspect_workbook_bytes,
    validate_workbook_patch_payload,
    validate_workbook_patch_receipt_payload,
)

__all__ = [
    "analyse_workbook_map",
    "build_plan",
    "compile_workbook_patch",
    "derive_workbook_evidence",
    "inspect_workbook",
    "inspect_workbook_bytes",
    "route_request",
    "validate_workbook_patch_payload",
    "validate_workbook_patch_receipt_payload",
]
__version__ = "0.3.0"
