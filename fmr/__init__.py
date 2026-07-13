"""Financial Model Router public API."""

from fmr.plan import build_plan
from fmr.router import route_request
from fmr.workbook import inspect_workbook, inspect_workbook_bytes

__all__ = ["build_plan", "route_request", "inspect_workbook", "inspect_workbook_bytes"]
__version__ = "0.2.0"
