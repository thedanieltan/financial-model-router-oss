from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

from fmr.core.jobs import ModelJob
from fmr.registry import RegisteredPackage


@runtime_checkable
class ProviderAdapter(Protocol):
    def compile(self, job: ModelJob, registered: RegisteredPackage) -> dict[str, Any]: ...


@runtime_checkable
class ProviderExecutor(Protocol):
    def execute(
        self,
        handoff: dict[str, Any],
        output_dir: Path,
        secrets: dict[str, str],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class PluginCatalog:
    adapter_loaders: dict[str, Callable[[], Any]]
    executor_loaders: dict[str, Callable[[], Any]]

    @classmethod
    def installed(cls) -> "PluginCatalog":
        return cls(
            _loaders("fmr.provider_adapters"),
            _loaders("fmr.provider_executors"),
        )

    def adapter(self, name: str) -> ProviderAdapter:
        return _instantiate(self.adapter_loaders, name, "adapter")

    def executor(self, name: str) -> ProviderExecutor:
        return _instantiate(self.executor_loaders, name, "executor")


def _loaders(group: str) -> dict[str, Callable[[], Any]]:
    return {item.name: item.load for item in metadata.entry_points().select(group=group)}


def _instantiate(loaders: dict[str, Callable[[], Any]], name: str, kind: str) -> Any:
    try:
        loaded = loaders[name]()
    except KeyError as exc:
        raise ValueError(f"provider {kind} entry point is not installed: {name}") from exc
    value = loaded() if isinstance(loaded, type) else loaded
    method = "compile" if kind == "adapter" else "execute"
    if not callable(getattr(value, method, None)):
        raise ValueError(f"provider {kind} entry point does not implement {method}(): {name}")
    return value
