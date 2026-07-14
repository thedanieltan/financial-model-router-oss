"""Native XLSX provider and provider-owned workbook runtime.

New code imports workbook capabilities from :mod:`fmr.providers.native_xlsx.workbook`.
The historical :mod:`fmr.workbook` namespace remains an import-compatible façade.
Provider execution helpers are resolved lazily so manifest discovery and imports
of provider-neutral modules never import OpenPyXL or executable provider code.
"""

from typing import Any

__all__ = ["execute_budget_forecast_handoff", "validate_budget_workbook"]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    from fmr.providers.native_xlsx import provider

    return getattr(provider, name)
