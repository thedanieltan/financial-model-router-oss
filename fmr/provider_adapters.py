"""Deprecated compatibility exports for provider adapters.

Provider implementations are now loaded from ``fmr.provider_adapters`` Python
entry points after route selection. This module remains importable for 1.0-alpha
callers but no longer contains a central provider switch.
"""

from fmr.provider_plugins import PluginCatalog, ProviderAdapter

__all__ = ["PluginCatalog", "ProviderAdapter"]
