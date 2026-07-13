"""Financial Model Router public API."""

from fmr.plan import build_plan
from fmr.router import route_request

__all__ = ["build_plan", "route_request"]
__version__ = "0.1.0"
