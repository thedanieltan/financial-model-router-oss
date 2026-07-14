"""Isolated entry point for one selected provider execution."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fmr.provider_plugins import PluginCatalog


def main() -> int:
    try:
        request: Any = json.load(sys.stdin)
        if not isinstance(request, dict) or set(request) != {"entry_point", "handoff", "output_dir", "secrets"}:
            raise ValueError("provider runner request is invalid")
        if not isinstance(request["entry_point"], str) or not isinstance(request["handoff"], dict) or not isinstance(request["output_dir"], str) or not isinstance(request["secrets"], dict):
            raise ValueError("provider runner request fields are invalid")
        executor = PluginCatalog.installed().executor(request["entry_point"])
        receipt = executor.execute(request["handoff"], Path(request["output_dir"]), request["secrets"])
        print(json.dumps({"status": "ok", "receipt": receipt}, sort_keys=True))
        return 0
    except Exception as exc:  # isolated process boundary
        print(json.dumps({"status": "error", "error_type": type(exc).__name__, "error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
