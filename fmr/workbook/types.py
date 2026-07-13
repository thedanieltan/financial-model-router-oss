from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Classification:
    value: str
    confidence: str
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class SheetMap:
    name: str
    position: int
    visibility: str
    used_range: str | None
    formula_cells: int
    value_cells: int
    merged_ranges: tuple[str, ...]
    detected_periods: tuple[str, ...]
    candidate_role: Classification
    candidate_metrics: tuple[str, ...]
    external_formula_references: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "position": self.position,
            "visibility": self.visibility,
            "used_range": self.used_range,
            "formula_cells": self.formula_cells,
            "value_cells": self.value_cells,
            "merged_ranges": list(self.merged_ranges),
            "detected_periods": list(self.detected_periods),
            "candidate_role": self.candidate_role.to_dict(),
            "candidate_metrics": list(self.candidate_metrics),
            "external_formula_references": self.external_formula_references,
        }


@dataclass(frozen=True)
class WorkbookMap:
    source_filename: str
    source_sha256: str
    source_size_bytes: int
    sheet_count: int
    defined_names: tuple[str, ...]
    external_links_detected: bool
    sheets: tuple[SheetMap, ...]
    findings: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": "workbook-map.v1",
            "source": {
                "filename": self.source_filename,
                "sha256": self.source_sha256,
                "size_bytes": self.source_size_bytes,
            },
            "workbook": {
                "sheet_count": self.sheet_count,
                "defined_names": list(self.defined_names),
                "external_links_detected": self.external_links_detected,
            },
            "sheets": [sheet.to_dict() for sheet in self.sheets],
            "findings": list(self.findings),
            "limitations": list(self.limitations),
        }
