from __future__ import annotations

import json
from importlib.resources import files
from typing import Any


_FIXTURES: dict[str, dict[str, str]] = {
    "dcf-ready": {
        "title": "DCF — ready",
        "description": "A complete operating-company DCF request.",
        "filename": "dcf-ready.json",
    },
    "debt-blocked": {
        "title": "Debt capacity — blocked",
        "description": "A refinancing request with missing debt and covenant inputs.",
        "filename": "debt-blocked.json",
    },
}


def list_fixtures() -> list[dict[str, str]]:
    return [
        {
            "fixture_id": fixture_id,
            "title": metadata["title"],
            "description": metadata["description"],
        }
        for fixture_id, metadata in sorted(_FIXTURES.items())
    ]


def load_fixture(fixture_id: str) -> dict[str, Any]:
    metadata = _FIXTURES.get(fixture_id)
    if metadata is None:
        raise KeyError(f"unknown fixture: {fixture_id}")
    resource = files("fmr.fixtures").joinpath(metadata["filename"])
    payload = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"fixture root must be an object: {fixture_id}")
    return payload
