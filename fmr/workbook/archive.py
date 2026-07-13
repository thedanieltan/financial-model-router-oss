from __future__ import annotations

import posixpath
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

MAX_COMPRESSED_BYTES = 20 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 2_000
MAX_SINGLE_ENTRY_BYTES = 20 * 1024 * 1024
MAX_SHEETS = 500


def validate_archive(archive: zipfile.ZipFile) -> set[str]:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise ValueError(f"workbook archive contains more than {MAX_ARCHIVE_ENTRIES} entries")
    total_uncompressed = 0
    names: set[str] = set()
    for info in infos:
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("workbook archive contains an unsafe path")
        if info.flag_bits & 0x1:
            raise ValueError("encrypted workbook entries are not supported")
        if info.file_size > MAX_SINGLE_ENTRY_BYTES:
            raise ValueError("workbook archive contains an oversized entry")
        total_uncompressed += info.file_size
        if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
            raise ValueError(f"workbook expands beyond {MAX_UNCOMPRESSED_BYTES} bytes")
        if info.compress_size == 0 and info.file_size > 0:
            raise ValueError("workbook archive contains an invalid compressed entry")
        if info.compress_size and info.file_size / info.compress_size > 1_000:
            raise ValueError("workbook archive contains an excessive compression ratio")
        names.add(info.filename)

    required = {"[Content_Types].xml", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
    missing = sorted(required - names)
    if missing:
        raise ValueError(f"workbook is missing required XLSX entries: {', '.join(missing)}")
    if any("vbaproject.bin" in name.lower() for name in names):
        raise ValueError("macro-enabled workbooks are not supported")
    return names


def read_entry(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        return archive.read(name)
    except KeyError as exc:
        raise ValueError(f"workbook is missing required entry: {name}") from exc


def parse_xml(payload: bytes, name: str) -> ET.Element:
    upper = payload[:4096].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError(f"workbook contains prohibited XML declarations in {name}")
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError(f"workbook contains invalid XML in {name}") from exc


def relationship_map(root: ET.Element, *, base: str) -> dict[str, tuple[str, str, str | None]]:
    relationships: dict[str, tuple[str, str, str | None]] = {}
    for node in root.findall(f"{{{PKG_REL_NS}}}Relationship"):
        relationship_id = node.attrib.get("Id")
        target = node.attrib.get("Target")
        relationship_type = node.attrib.get("Type", "")
        target_mode = node.attrib.get("TargetMode")
        if not relationship_id or not target:
            continue
        if target_mode == "External":
            resolved = target
        elif target.startswith("/"):
            resolved = target.lstrip("/")
        else:
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(base), target))
            if resolved.startswith("../") or resolved == "..":
                raise ValueError("workbook contains an unsafe relationship target")
        relationships[relationship_id] = (resolved, relationship_type, target_mode)
    return relationships


def load_shared_strings(archive: zipfile.ZipFile, names: set[str]) -> tuple[str, ...]:
    name = "xl/sharedStrings.xml"
    if name not in names:
        return ()
    root = parse_xml(read_entry(archive, name), name)
    values: list[str] = []
    for item in root.findall(f"{{{MAIN_NS}}}si"):
        text = "".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t"))
        values.append(text)
    return tuple(values)


def defined_names(workbook_root: ET.Element) -> tuple[str, ...]:
    parent = workbook_root.find(f"{{{MAIN_NS}}}definedNames")
    if parent is None:
        return ()
    return tuple(sorted({
        node.attrib["name"]
        for node in parent.findall(f"{{{MAIN_NS}}}definedName")
        if node.attrib.get("name")
    }))
