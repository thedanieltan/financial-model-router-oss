from __future__ import annotations

import hashlib
import io
import json
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
    defined_names,
    load_shared_strings,
    parse_xml,
    read_entry,
    relationship_map,
    validate_archive,
)
from fmr.providers.native_xlsx.workbook.classify import (
    classify_metric_label,
    classify_period_label,
    is_period_label,
)
from fmr.providers.native_xlsx.workbook.inspect import inspect_workbook_bytes

_SUPPORTED_EXTENSION = ".xlsx"
_CELL_RE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
_CROSS_SHEET_REF_RE = re.compile(
    r"(?P<external>\[[^\]]+\])?(?P<sheet>'(?:[^']|'')+'|[A-Za-z0-9_.]+)!"
    r"(?P<range>\$?[A-Z]{1,3}\$?[1-9][0-9]*(?::\$?[A-Z]{1,3}\$?[1-9][0-9]*)?)",
    re.IGNORECASE,
)
_LOCAL_REF_RE = re.compile(
    r"(?<![A-Za-z0-9_!])(?P<range>\$?[A-Z]{1,3}\$?[1-9][0-9]*(?::\$?[A-Z]{1,3}\$?[1-9][0-9]*)?)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_CURRENCY_CODES = (
    "USD", "SGD", "EUR", "GBP", "JPY", "AUD", "CAD", "CNY", "HKD", "INR",
    "CHF", "NZD", "MYR", "IDR", "THB", "PHP", "KRW",
)
_CURRENCY_SYMBOLS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<![A-Za-z])S\$(?![A-Za-z])", re.IGNORECASE), "SGD"),
    (re.compile(r"(?<![A-Za-z])US\$(?![A-Za-z])", re.IGNORECASE), "USD"),
    (re.compile(r"(?<![A-Za-z])HK\$(?![A-Za-z])", re.IGNORECASE), "HKD"),
    (re.compile(r"(?<![A-Za-z])(?:A\$|AU\$)(?![A-Za-z])", re.IGNORECASE), "AUD"),
    (re.compile(r"(?<![A-Za-z])(?:C\$|CA\$)(?![A-Za-z])", re.IGNORECASE), "CAD"),
    (re.compile(r"£"), "GBP"),
    (re.compile(r"€"), "EUR"),
    (re.compile(r"₹"), "INR"),
)
_SCALE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:in\s+)?(?:thousands|thousand|000s|000's)\b", re.IGNORECASE), "thousands"),
    (re.compile(r"\b(?:in\s+)?(?:millions|million|mn|mm)\b", re.IGNORECASE), "millions"),
    (re.compile(r"\b(?:in\s+)?(?:billions|billion|bn)\b", re.IGNORECASE), "billions"),
)


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def map_workbook_semantics(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.suffix.lower() != _SUPPORTED_EXTENSION:
        raise ValueError("only .xlsx workbooks are supported")
    data = source.read_bytes()
    before = hashlib.sha256(data).hexdigest()
    result = map_workbook_semantics_bytes(data, filename=source.name)
    after = hashlib.sha256(source.read_bytes()).hexdigest()
    if before != after or result["source"]["sha256"] != before:
        raise RuntimeError("source workbook changed during semantic mapping")
    return result


def map_workbook_semantics_bytes(data: bytes, *, filename: str) -> dict[str, Any]:
    if Path(filename).suffix.lower() != _SUPPORTED_EXTENSION:
        raise ValueError("only .xlsx workbooks are supported")
    if not data:
        raise ValueError("workbook is empty")
    if len(data) > MAX_COMPRESSED_BYTES:
        raise ValueError(f"workbook exceeds {MAX_COMPRESSED_BYTES} compressed bytes")

    structural_map = inspect_workbook_bytes(data, filename=filename)
    structural_payload = structural_map.to_dict()
    source = {
        "filename": structural_map.source_filename,
        "sha256": structural_map.source_sha256,
        "size_bytes": structural_map.source_size_bytes,
    }
    structural_by_name = {sheet.name: sheet for sheet in structural_map.sheets}

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("workbook is not a valid XLSX archive") from exc

    semantic_sheets: list[dict[str, Any]] = []
    cross_sheet: list[dict[str, Any]] = []
    findings: list[str] = []
    with archive:
        names = validate_archive(archive)
        workbook_root = parse_xml(read_entry(archive, "xl/workbook.xml"), "xl/workbook.xml")
        rels = relationship_map(
            parse_xml(read_entry(archive, "xl/_rels/workbook.xml.rels"), "xl/_rels/workbook.xml.rels"),
            base="xl/workbook.xml",
        )
        shared_strings = load_shared_strings(archive, names)
        _ = defined_names(workbook_root)
        sheets_element = workbook_root.find(f"{{{MAIN_NS}}}sheets")
        if sheets_element is None:
            raise ValueError("workbook does not contain a sheets collection")

        for sheet_node in sheets_element:
            sheet_name = sheet_node.attrib.get("name", "")
            relationship_id = sheet_node.attrib.get(f"{{{DOC_REL_NS}}}id")
            if not sheet_name or not relationship_id or relationship_id not in rels:
                raise ValueError("workbook contains an invalid sheet relationship")
            sheet_path, relationship_type, target_mode = rels[relationship_id]
            if target_mode == "External" or "worksheet" not in relationship_type:
                continue
            structural_sheet = structural_by_name.get(sheet_name)
            if structural_sheet is None:
                continue
            cells = _read_cells(archive, sheet_path, shared_strings)
            period_columns = _period_columns(cells)
            metric_rows = _metric_rows(cells, period_columns)
            currency_evidence = _currency_evidence(cells)
            scale_evidence = _scale_evidence(cells)
            dependencies = _formula_dependencies(cells)
            for dependency in dependencies:
                for reference in dependency["references"]:
                    if reference["sheet"] and (reference["sheet"] != sheet_name or reference["external"]):
                        cross_sheet.append({
                            "from_sheet": sheet_name,
                            "formula_cell": dependency["formula_cell"],
                            "to_sheet": reference["sheet"],
                            "target_range": reference["range"],
                            "external": reference["external"],
                        })
            if not period_columns:
                findings.append(f"no_period_columns:{sheet_name}")
            if structural_sheet.candidate_role.value != "unknown" and not metric_rows:
                findings.append(f"no_recognized_metric_rows:{sheet_name}")
            semantic_sheets.append({
                "name": sheet_name,
                "role": structural_sheet.candidate_role.to_dict(),
                "period_columns": period_columns,
                "metric_rows": metric_rows,
                "currency_evidence": currency_evidence,
                "scale_evidence": scale_evidence,
                "formula_dependencies": dependencies,
            })

    cross_sheet = _deduplicate_dicts(cross_sheet, ("from_sheet", "formula_cell", "to_sheet", "target_range", "external"))
    limitations = [
        "financial numeric cell values are intentionally excluded from the semantic map",
        "currency and scale are inferred only from explicit textual evidence, never from magnitude",
        "unmarked periods remain unspecified rather than being guessed as actual, budget or forecast",
        "formula lineage records direct A1 and range references but does not interpret full Excel formula semantics",
        "charts, pivots, drawings and formatting are not used as financial-semantic evidence",
    ]
    if structural_map.external_links_detected:
        findings.append("external_links_detected")
    return {
        "contract_version": "workbook-semantic-map.v1",
        "source": source,
        "structural_map_sha256": _digest(structural_payload),
        "sheets": semantic_sheets,
        "cross_sheet_dependencies": cross_sheet,
        "findings": list(dict.fromkeys(findings)),
        "limitations": limitations,
    }


def _read_cells(
    archive: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    root = parse_xml(read_entry(archive, sheet_path), sheet_path)
    cells: dict[str, dict[str, Any]] = {}
    sheet_data = root.find(f"{{{MAIN_NS}}}sheetData")
    if sheet_data is None:
        return cells
    for cell in sheet_data.iter(f"{{{MAIN_NS}}}c"):
        coordinate = cell.attrib.get("r", "").upper()
        parsed = _parse_coordinate(coordinate)
        if parsed is None:
            continue
        row, column = parsed
        formula_node = cell.find(f"{{{MAIN_NS}}}f")
        formula = formula_node.text if formula_node is not None and formula_node.text else None
        value = _cell_value(cell, shared_strings)
        cells[coordinate] = {
            "coordinate": coordinate,
            "row": row,
            "column": column,
            "value": value,
            "formula": formula,
            "cell_kind": "formula" if formula_node is not None else "value" if value not in (None, "") else "blank",
        }
    return cells


def _period_columns(cells: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for cell in cells.values():
        if is_period_label(cell["value"]):
            candidates[cell["row"]].append(cell)
    if not candidates:
        return []
    header_row = sorted(candidates, key=lambda row: (-len(candidates[row]), row))[0]
    result: list[dict[str, Any]] = []
    for cell in sorted(candidates[header_row], key=lambda item: item["column"]):
        classification = classify_period_label(cell["value"])
        result.append({
            "coordinate": cell["coordinate"],
            "column": cell["column"],
            "label": str(cell["value"]).strip(),
            "classification": classification.to_dict(),
        })
    return result


def _metric_rows(cells: dict[str, dict[str, Any]], period_columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for cell in cells.values():
        rows[cell["row"]].append(cell)
    period_by_column = {item["column"]: item for item in period_columns}
    first_period_column = min(period_by_column) if period_by_column else None
    result: list[dict[str, Any]] = []
    for row_number in sorted(rows):
        row_cells = sorted(rows[row_number], key=lambda item: item["column"])
        label_candidates = [
            cell for cell in row_cells
            if isinstance(cell["value"], str)
            and cell["value"].strip()
            and (first_period_column is None or cell["column"] < first_period_column)
        ]
        classified: list[tuple[dict[str, Any], Any]] = []
        for cell in label_candidates:
            metric = classify_metric_label(cell["value"])
            if metric.value != "unknown":
                classified.append((cell, metric))
        if not classified:
            continue
        highest_confidence = max(2 if metric.confidence == "high" else 1 for _, metric in classified)
        best = [(cell, metric) for cell, metric in classified if (2 if metric.confidence == "high" else 1) == highest_confidence]
        metric_values = {metric.value for _, metric in best}
        if len(metric_values) != 1:
            continue
        label_cell, metric = best[0]
        cell_by_column = {cell["column"]: cell for cell in row_cells}
        period_cells: list[dict[str, Any]] = []
        for column, period in sorted(period_by_column.items()):
            target = cell_by_column.get(column)
            period_cells.append({
                "coordinate": target["coordinate"] if target else f"{_column_name(column)}{row_number}",
                "period_label": period["label"],
                "period_kind": period["classification"]["value"],
                "cell_kind": target["cell_kind"] if target else "blank",
            })
        result.append({
            "row": row_number,
            "label_cell": label_cell["coordinate"],
            "label": str(label_cell["value"]).strip(),
            "metric": metric.to_dict(),
            "period_cells": period_cells,
        })
    return result


def _currency_evidence(cells: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: dict[str, list[str]] = defaultdict(list)
    for cell in cells.values():
        if not isinstance(cell["value"], str) or not cell["value"].strip():
            continue
        text = cell["value"].strip()
        upper = text.upper()
        for code in _CURRENCY_CODES:
            if re.search(rf"(?<![A-Z]){code}(?![A-Z])", upper):
                evidence[code].append(f"cell:{cell['coordinate']}:explicit currency code {code}")
        for pattern, code in _CURRENCY_SYMBOLS:
            if pattern.search(text):
                evidence[code].append(f"cell:{cell['coordinate']}:explicit currency marker")
    return [
        {"value": code, "confidence": "high", "evidence": list(dict.fromkeys(items))}
        for code, items in sorted(evidence.items())
    ]


def _scale_evidence(cells: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: dict[str, list[str]] = defaultdict(list)
    for cell in cells.values():
        if not isinstance(cell["value"], str) or not cell["value"].strip():
            continue
        text = cell["value"].strip()
        for pattern, scale in _SCALE_PATTERNS:
            if pattern.search(text):
                evidence[scale].append(f"cell:{cell['coordinate']}:explicit scale marker")
    return [
        {"value": scale, "confidence": "high", "evidence": list(dict.fromkeys(items))}
        for scale, items in sorted(evidence.items())
    ]


def _formula_dependencies(cells: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    dependencies: list[dict[str, Any]] = []
    for cell in sorted(cells.values(), key=lambda item: (item["row"], item["column"])):
        formula = cell.get("formula")
        if not isinstance(formula, str) or not formula.strip():
            continue
        references = _formula_references(formula)
        dependencies.append({
            "formula_cell": cell["coordinate"],
            "formula_sha256": hashlib.sha256(formula.encode("utf-8")).hexdigest(),
            "references": references,
        })
    return dependencies


def _formula_references(formula: str) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    for match in _CROSS_SHEET_REF_RE.finditer(formula):
        sheet = match.group("sheet")
        if sheet.startswith("'") and sheet.endswith("'"):
            sheet = sheet[1:-1].replace("''", "'")
        references.append({
            "sheet": sheet,
            "range": _normalize_range(match.group("range")),
            "external": bool(match.group("external")),
        })
        occupied.append(match.span())
    for match in _LOCAL_REF_RE.finditer(formula):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        references.append({
            "sheet": None,
            "range": _normalize_range(match.group("range")),
            "external": False,
        })
    return _deduplicate_dicts(references, ("sheet", "range", "external"))


def _normalize_range(value: str) -> str:
    return value.replace("$", "").upper()


def _deduplicate_dicts(values: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for value in values:
        key = tuple(value[field] for field in fields)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


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
    match = _CELL_RE.fullmatch(coordinate.upper())
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
