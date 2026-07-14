"""Target ownership boundary for the existing workbook implementation.

The migration occurs in WP6. Import from ``fmr.workbook`` until compatibility
wrappers are redirected through this provider.
"""

from fmr.providers.native_xlsx.provider import execute_budget_forecast_handoff, validate_budget_workbook

__all__ = ["execute_budget_forecast_handoff", "validate_budget_workbook"]
