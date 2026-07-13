"""Financial Model Router public API."""

from fmr.plan import build_plan
from fmr.router import route_request
from fmr.workbook import (
    analyse_workbook_map,
    derive_workbook_evidence,
    inspect_workbook,
    inspect_workbook_bytes,
)

__all__ = [
    "analyse_workbook_map",
    "build_plan",
    "derive_workbook_evidence",
    "inspect_workbook",
    "inspect_workbook_bytes",
    "route_request",
]
__version__ = "0.2.1"
