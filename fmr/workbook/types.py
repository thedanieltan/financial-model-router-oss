from __future__ import annotations

from dataclasses import dataclass
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

    @classmethod
    def from_mapping(cls, data: Any) -> "Classification":
        if not isinstance(data, dict):
            raise ValueError("candidate_role must be an object")
        value = data.get("value")
        confidence = data.get("confidence")
        evidence = data.get("evidence")
        if not isinstance(value, str) or not value:
            raise ValueError("candidate_role.value must be a non-empty string")
        if confidence not in {"low", "medium", "high"}:
            raise ValueError("candidate_role.confidence is invalid")
        if not isinstance(evidence, list) or not all(
            isinstance(item, str) for item in evidence
        ):
            raise ValueError("candidate_role.evidence must be an array of strings")
        return cls(value=value, confidence=confidence, evidence=tuple(evidence))


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

    @classmethod
    def from_mapping(cls, data: Any) -> "SheetMap":
        if not isinstance(data, dict):
            raise ValueError("workbook-map sheets entries must be objects")
        name = data.get("name")
        position = data.get("position")
        visibility = data.get("visibility")
        used_range = data.get("used_range")
        formula_cells = data.get("formula_cells")
        value_cells = data.get("value_cells")
        external_formula_references = data.get("external_formula_references")
        if not isinstance(name, str) or not name:
            raise ValueError("sheet name must be a non-empty string")
        if not isinstance(position, int) or position < 1:
            raise ValueError("sheet position must be a positive integer")
        if visibility not in {"visible", "hidden", "veryHidden"}:
            raise ValueError("sheet visibility is invalid")
        if used_range is not None and not isinstance(used_range, str):
            raise ValueError("sheet used_range must be a string or null")
        for field, value in {
            "formula_cells": formula_cells,
            "value_cells": value_cells,
            "external_formula_references": external_formula_references,
        }.items():
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"sheet {field} must be a non-negative integer")
        return cls(
            name=name,
            position=position,
            visibility=visibility,
            used_range=used_range,
            formula_cells=formula_cells,
            value_cells=value_cells,
            merged_ranges=_string_tuple(data.get("merged_ranges"), "merged_ranges"),
            detected_periods=_string_tuple(
                data.get("detected_periods"), "detected_periods"
            ),
            candidate_role=Classification.from_mapping(data.get("candidate_role")),
            candidate_metrics=_string_tuple(
                data.get("candidate_metrics"), "candidate_metrics"
            ),
            external_formula_references=external_formula_references,
        )


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

    @classmethod
    def from_mapping(cls, data: Any) -> "WorkbookMap":
        if not isinstance(data, dict) or data.get("contract_version") != "workbook-map.v1":
            raise ValueError("unsupported workbook-map contract_version")
        source = data.get("source")
        workbook = data.get("workbook")
        sheets = data.get("sheets")
        if not isinstance(source, dict) or not isinstance(workbook, dict):
            raise ValueError("workbook-map source and workbook must be objects")
        filename = source.get("filename")
        sha256 = source.get("sha256")
        size_bytes = source.get("size_bytes")
        sheet_count = workbook.get("sheet_count")
        external_links = workbook.get("external_links_detected")
        if not isinstance(filename, str) or not filename:
            raise ValueError("workbook-map source.filename must be a non-empty string")
        if not isinstance(sha256, str) or len(sha256) != 64:
            raise ValueError("workbook-map source.sha256 must be a SHA-256 hex string")
        if not isinstance(size_bytes, int) or size_bytes < 0:
            raise ValueError(
                "workbook-map source.size_bytes must be a non-negative integer"
            )
        if not isinstance(sheet_count, int) or sheet_count < 0:
            raise ValueError(
                "workbook-map workbook.sheet_count must be a non-negative integer"
            )
        if not isinstance(external_links, bool):
            raise ValueError(
                "workbook-map workbook.external_links_detected must be boolean"
            )
        if not isinstance(sheets, list):
            raise ValueError("workbook-map sheets must be an array")
        parsed_sheets = tuple(SheetMap.from_mapping(item) for item in sheets)
        if sheet_count != len(parsed_sheets):
            raise ValueError("workbook-map sheet_count does not match sheets")
        return cls(
            source_filename=filename,
            source_sha256=sha256,
            source_size_bytes=size_bytes,
            sheet_count=sheet_count,
            defined_names=_string_tuple(
                workbook.get("defined_names"), "defined_names"
            ),
            external_links_detected=external_links,
            sheets=parsed_sheets,
            findings=_string_tuple(data.get("findings"), "findings"),
            limitations=_string_tuple(data.get("limitations"), "limitations"),
        )


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be an array of strings")
    return tuple(value)
