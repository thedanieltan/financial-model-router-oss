from __future__ import annotations

import io
import zipfile
from html import escape
from typing import Any


def build_xlsx(
    sheets: list[dict[str, Any]],
    *,
    defined_names: tuple[str, ...] = (),
    external_link: bool = False,
    include_chart: bool = False,
) -> bytes:
    workbook_sheets: list[str] = []
    workbook_rels: list[str] = []
    overrides: list[str] = []
    worksheet_entries: dict[str, str] = {}

    for index, sheet in enumerate(sheets, start=1):
        state = f' state="{escape(sheet.get("state", "visible"))}"' if sheet.get("state", "visible") != "visible" else ""
        workbook_sheets.append(
            f'<sheet name="{escape(sheet["name"])}" sheetId="{index}" r:id="rId{index}"{state}/>'
        )
        workbook_rels.append(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
        overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        worksheet_entries[f"xl/worksheets/sheet{index}.xml"] = _sheet_xml(sheet.get("cells", {}), sheet.get("merged", ()))

    defined_xml = ""
    if defined_names:
        entries = "".join(
            f'<definedName name="{escape(name)}">Sheet1!$A$1</definedName>' for name in defined_names
        )
        defined_xml = f"<definedNames>{entries}</definedNames>"

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{"".join(workbook_sheets)}</sheets>{defined_xml}</workbook>'
    )
    relationships = list(workbook_rels)
    relationships.append(
        '<Relationship Id="rIdStyles" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    extra_entries: dict[str, str] = {}
    if external_link:
        relationships.append(
            '<Relationship Id="rIdExternal" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink" '
            'Target="externalLinks/externalLink1.xml"/>'
        )
        overrides.append(
            '<Override PartName="/xl/externalLinks/externalLink1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.externalLink+xml"/>'
        )
        extra_entries["xl/externalLinks/externalLink1.xml"] = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<externalLink xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'
        )
    if include_chart:
        overrides.append(
            '<Override PartName="/xl/charts/chart1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>'
        )
        extra_entries["xl/charts/chart1.xml"] = '<chartSpace xmlns="http://schemas.openxmlformats.org/drawingml/2006/chart"/>'

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        f'{"".join(overrides)}</Types>'
    )
    package_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{"".join(relationships)}</Relationships>'
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font/></fonts><fills count="1"><fill/></fills>'
        '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
        '<cellXfs count="1"><xf xfId="0"/></cellXfs></styleSheet>'
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", package_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        archive.writestr("xl/styles.xml", styles)
        for name, content in worksheet_entries.items():
            archive.writestr(name, content)
        for name, content in extra_entries.items():
            archive.writestr(name, content)
    return output.getvalue()


def financial_workbook(
    *,
    external_link: bool = False,
    include_chart: bool = True,
) -> bytes:
    formula = "[Source.xlsx]Sheet1!A1" if external_link else "C3*1.10"
    return build_xlsx(
        [
            {
                "name": "Income Statement",
                "cells": {
                    "A1": "Income Statement",
                    "B2": 2024,
                    "C2": 2025,
                    "D2": "2026E",
                    "A3": "Revenue",
                    "B3": 100,
                    "C3": 120,
                    "D3": {"formula": formula, "value": 132},
                    "A4": "EBITDA",
                    "B4": 20,
                    "C4": 24,
                    "D4": {"formula": "D3*0.20", "value": 26.4},
                    "A5": "Net Income",
                },
                "merged": ("A1:D1",),
            },
            {
                "name": "Balance Sheet",
                "state": "hidden",
                "cells": {
                    "A1": "Balance Sheet",
                    "A3": "Total Assets",
                    "A4": "Total Liabilities",
                    "A5": "Total Equity",
                    "B2": 2024,
                    "C2": 2025,
                },
            },
            {
                "name": "Assumptions",
                "cells": {
                    "A1": "Assumptions",
                    "A3": "Growth Rate",
                    "A4": "Tax Rate",
                    "A5": "WACC",
                },
            },
        ],
        defined_names=("ForecastStart",),
        external_link=external_link,
        include_chart=include_chart,
    )


def _sheet_xml(cells: dict[str, Any], merged: tuple[str, ...]) -> str:
    rows: dict[int, list[tuple[str, Any]]] = {}
    for coordinate, value in cells.items():
        row = int("".join(character for character in coordinate if character.isdigit()))
        rows.setdefault(row, []).append((coordinate, value))
    row_xml: list[str] = []
    for row_number in sorted(rows):
        cell_xml = "".join(_cell_xml(coordinate, value) for coordinate, value in sorted(rows[row_number]))
        row_xml.append(f'<row r="{row_number}">{cell_xml}</row>')
    dimensions = _dimension(cells)
    merges = ""
    if merged:
        merge_xml = "".join(f'<mergeCell ref="{escape(ref)}"/>' for ref in merged)
        merges = f'<mergeCells count="{len(merged)}">{merge_xml}</mergeCells>'
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="{dimensions}"/><sheetData>{"".join(row_xml)}</sheetData>{merges}</worksheet>'
    )


def _cell_xml(coordinate: str, value: Any) -> str:
    if isinstance(value, dict):
        formula = escape(str(value["formula"]))
        cached = escape(str(value.get("value", "")))
        return f'<c r="{coordinate}"><f>{formula}</f><v>{cached}</v></c>'
    if isinstance(value, str):
        return f'<c r="{coordinate}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
    return f'<c r="{coordinate}"><v>{escape(str(value))}</v></c>'


def _dimension(cells: dict[str, Any]) -> str:
    if not cells:
        return "A1"
    coordinates = list(cells)
    rows = [int("".join(ch for ch in coordinate if ch.isdigit())) for coordinate in coordinates]
    columns = [_column_number("".join(ch for ch in coordinate if ch.isalpha())) for coordinate in coordinates]
    return f'{_column_name(min(columns))}{min(rows)}:{_column_name(max(columns))}{max(rows)}'


def _column_number(letters: str) -> int:
    value = 0
    for character in letters:
        value = value * 26 + ord(character.upper()) - 64
    return value


def _column_name(column: int) -> str:
    value = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        value = chr(65 + remainder) + value
    return value
