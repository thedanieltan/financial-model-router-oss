from __future__ import annotations

import hashlib
import io
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from fmr.providers.native_xlsx.workbook.archive import (
    DOC_REL_NS,
    MAIN_NS,
    MAX_COMPRESSED_BYTES,
    MAX_SHEETS,
    defined_names,
    load_shared_strings,
    parse_xml,
    read_entry,
    relationship_map,
    validate_archive,
)
from fmr.providers.native_xlsx.workbook.classify import classify_sheet, detect_metrics, detect_periods
from fmr.providers.native_xlsx.workbook.types import SheetMap, WorkbookMap

_SUPPORTED_EXTENSION = ".xlsx"
_FORBIDDEN_MACRO_MARKERS = ("vbaproject.bin", "macroenabled")
_CELL_RE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
_EXTERNAL_FORMULA_RE = re.compile(r"\[[^\]]+\]")


def inspect_workbook(path: str | Path) -> WorkbookMap:
    source = Path(path)
    if source.suffix.lower() != _SUPPORTED_EXTENSION:
        raise ValueError("only .xlsx workbooks are supported")
    data = source.read_bytes()
    before = hashlib.sha256(data).hexdigest()
    result = inspect_workbook_bytes(data, filename=source.name)
    after = hashlib.sha256(source.read_bytes()).hexdigest()
    if before != after or result.source_sha256 != before:
        raise RuntimeError("source workbook changed during inspection")
    return result


def inspect_workbook_bytes(data: bytes, *, filename: str) -> WorkbookMap:
    if Path(filename).suffix.lower() != _SUPPORTED_EXTENSION:
        raise ValueError("only .xlsx workbooks are supported")
    if not data:
        raise ValueError("workbook is empty")
    if len(data) > MAX_COMPRESSED_BYTES:
        raise ValueError(f"workbook exceeds {MAX_COMPRESSED_BYTES} compressed bytes")

    source_hash = hashlib.sha256(data).hexdigest()
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("workbook is not a valid XLSX archive") from exc

    with archive:
        names = validate_archive(archive)
        content_types = read_entry(archive, "[Content_Types].xml").lower()
        if any(marker.encode("ascii") in content_types for marker in _FORBIDDEN_MACRO_MARKERS):
            raise ValueError("macro-enabled workbooks are not supported")

        workbook_root = parse_xml(read_entry(archive, "xl/workbook.xml"), "xl/workbook.xml")
        rels = relationship_map(
            parse_xml(read_entry(archive, "xl/_rels/workbook.xml.rels"), "xl/_rels/workbook.xml.rels"),
            base="xl/workbook.xml",
        )
        shared_strings = load_shared_strings(archive, names)
        workbook_names = defined_names(workbook_root)
        external_links = any(name.startswith("xl/externalLinks/") for name in names)
        findings: list[str] = []
        limitations = (
            "formula results are not recalculated",
            "cell formatting is not interpreted as financial meaning",
            "charts, pivots and drawings are reported only as unsupported features",
        )
        for feature, prefix in {
            "charts": "xl/charts/",
            "pivot tables": "xl/pivotTables/",
            "drawings": "xl/drawings/",
        }.items():
            if any(name.startswith(prefix) for name in names):
                findings.append(f"unsupported_feature:{feature}")

        sheets_element = workbook_root.find(f"{{{MAIN_NS}}}sheets")
        if sheets_element is None:
            raise ValueError("workbook does not contain a sheets collection")
        sheet_nodes = list(sheets_element)
        if len(sheet_nodes) > MAX_SHEETS:
            raise ValueError(f"workbook contains more than {MAX_SHEETS} sheets")

        sheet_maps: list[SheetMap] = []
        for position, sheet_node in enumerate(sheet_nodes, start=1):
            sheet_name = sheet_node.attrib.get("name", "")
            relationship_id = sheet_node.attrib.get(f"{{{DOC_REL_NS}}}id")
            if not sheet_name or not relationship_id or relationship_id not in rels:
                raise ValueError("workbook contains an invalid sheet relationship")
            sheet_path, relationship_type, target_mode = rels[relationship_id]
            if target_mode == "External":
                external_links = True
                findings.append(f"external_sheet_relationship:{sheet_name}")
                continue
            if "worksheet" not in relationship_type:
                findings.append(f"unsupported_sheet_type:{sheet_name}")
                continue
            visibility = sheet_node.attrib.get("state", "visible")
            if visibility not in {"visible", "hidden", "veryHidden"}:
                raise ValueError(f"workbook contains an invalid visibility state for sheet: {sheet_name}")
            sheet_map = _inspect_sheet(
                archive,
                sheet_path,
                sheet_name=sheet_name,
                position=position,
                visibility=visibility,
                shared_strings=shared_strings,
            )
            if sheet_map.visibility != "visible":
                findings.append(f"hidden_sheet:{sheet_map.name}:{sheet_map.visibility}")
            if sheet_map.external_formula_references:
                external_links = True
            sheet_maps.append(sheet_map)

        if external_links:
            findings.append("external_links_detected")
        return WorkbookMap(
            source_filename=Path(filename).name,
            source_sha256=source_hash,
            source_size_bytes=len(data),
            sheet_count=len(sheet_nodes),
            defined_names=workbook_names,
            external_links_detected=external_links,
            sheets=tuple(sheet_maps),
            findings=tuple(dict.fromkeys(findings)),
            limitations=limitations,
        )


def _inspect_sheet(
    archive: zipfile.ZipFile,
    sheet_path: str,
    *,
    sheet_name: str,
    position: int,
    visibility: str,
    shared_strings: tuple[str, ...],
) -> SheetMap:
    root = parse_xml(read_entry(archive, sheet_path), sheet_path)
    dimension = root.find(f"{{{MAIN_NS}}}dimension")
    declared_range = dimension.attrib.get("ref") if dimension is not None else None
    rows: dict[int, list[tuple[int, Any]]] = defaultdict(list)
    formula_cells = value_cells = external_formula_references = 0
    min_row = min_col = max_row = max_col = None

    sheet_data = root.find(f"{{{MAIN_NS}}}sheetData")
    if sheet_data is not None:
        for cell in sheet_data.iter(f"{{{MAIN_NS}}}c"):
            parsed = _parse_coordinate(cell.attrib.get("r"))
            if parsed is None:
                continue
            row_number, column_number = parsed
            formula_node = cell.find(f"{{{MAIN_NS}}}f")
            formula = formula_node.text if formula_node is not None else None
            if formula_node is not None:
                formula_cells += 1
                if formula and _EXTERNAL_FORMULA_RE.search(formula):
                    external_formula_references += 1
            value = _cell_value(cell, shared_strings)
            if formula_node is None and value not in (None, ""):
                value_cells += 1
            rows[row_number].append((column_number, value))
            min_row = row_number if min_row is None else min(min_row, row_number)
            max_row = row_number if max_row is None else max(max_row, row_number)
            min_col = column_number if min_col is None else min(min_col, column_number)
            max_col = column_number if max_col is None else max(max_col, column_number)

    used_range = declared_range
    if declared_range in (None, "A1") and min_row is not None:
        used_range = f"{_column_name(min_col or 1)}{min_row}:{_column_name(max_col or 1)}{max_row}"
    merged_parent = root.find(f"{{{MAIN_NS}}}mergeCells")
    merged_ranges = tuple(
        node.attrib["ref"]
        for node in (list(merged_parent) if merged_parent is not None else [])
        if node.attrib.get("ref")
    )

    values_by_row: list[list[Any]] = []
    labels: list[str] = []
    for row_number in sorted(rows):
        ordered = [item[1] for item in sorted(rows[row_number], key=lambda item: item[0])]
        values_by_row.append(ordered)
        label = next((str(value).strip() for value in ordered if isinstance(value, str) and value.strip()), None)
        if label:
            labels.append(label)

    return SheetMap(
        name=sheet_name,
        position=position,
        visibility=visibility,
        used_range=used_range,
        formula_cells=formula_cells,
        value_cells=value_cells,
        merged_ranges=merged_ranges,
        detected_periods=detect_periods(values_by_row),
        candidate_role=classify_sheet(sheet_name, labels),
        candidate_metrics=detect_metrics(labels),
        external_formula_references=external_formula_references,
    )


def _cell_value(cell: ET.Element, shared_strings: tuple[str, ...]) -> Any:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t"))
    value_node = cell.find(f"{{{MAIN_NS}}}v")
    if value_node is None or value_node.text is None:
        return None
    raw = value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return raw
    if cell_type == "b":
        return raw == "1"
    if cell_type in {"str", "e"}:
        return raw
    try:
        number = float(raw)
    except ValueError:
        return raw
    return int(number) if number.is_integer() else number


def _parse_coordinate(coordinate: str | None) -> tuple[int, int] | None:
    if not coordinate:
        return None
    match = _CELL_RE.match(coordinate.upper())
    if not match:
        return None
    letters, row_text = match.groups()
    column = 0
    for character in letters:
        column = column * 26 + ord(character) - 64
    return int(row_text), column


def _column_name(column: int) -> str:
    result = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        result = chr(65 + remainder) + result
    return result
