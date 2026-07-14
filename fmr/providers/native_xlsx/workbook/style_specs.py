from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from fmr.providers.native_xlsx.workbook.content_specs import CONTENT_SPECS

_HEX_RE = re.compile(r"^#[0-9A-F]{6}$")
_ALLOWED_ALIGNMENTS = {"center", "left", "right"}
_ALLOWED_BORDER_STYLES = {"none", "thin"}
_ALLOWED_NUMBER_TYPES = {
    "boolean",
    "currency",
    "days",
    "decimal",
    "integer",
    "multiple",
    "percentage",
    "period",
    "preserve_source",
    "text",
    "years",
}


@dataclass(frozen=True)
class WorkbookStyleSpec:
    format_role: str
    font_family: str
    font_size: int
    bold: bool
    italic: bool
    font_colour: str
    fill_colour: str
    horizontal_alignment: str
    wrap_text: bool
    border_bottom: str
    locked: bool

    @property
    def specification_ref(self) -> str:
        return f"fmr://workbook-style-specs/roles/{self.format_role}/v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": "workbook-style-spec.v1",
            "specification_ref": self.specification_ref,
            "format_role": self.format_role,
            "font": {
                "family": self.font_family,
                "size": self.font_size,
                "bold": self.bold,
                "italic": self.italic,
                "colour": self.font_colour,
            },
            "fill": {"colour": self.fill_colour},
            "alignment": {
                "horizontal": self.horizontal_alignment,
                "wrap_text": self.wrap_text,
            },
            "border": {"bottom": self.border_bottom},
            "protection": {"locked": self.locked},
        }


@dataclass(frozen=True)
class NumberFormatSpec:
    semantic_type: str
    code: str

    @property
    def specification_ref(self) -> str:
        return f"fmr://workbook-style-specs/number-formats/{self.semantic_type}/v1"

    def to_dict(self) -> dict[str, str]:
        return {
            "contract_version": "workbook-number-format-spec.v1",
            "specification_ref": self.specification_ref,
            "semantic_type": self.semantic_type,
            "code": self.code,
        }


PALETTE = {
    "border": "#D1D5DB",
    "control_fill": "#FDECEC",
    "control_text": "#9B1C1C",
    "header_fill": "#E5E7EB",
    "input_fill": "#FFF4CC",
    "input_text": "#1D4ED8",
    "output_fill": "#EAF2F8",
    "primary_text": "#111827",
    "reference_text": "#6B7280",
    "section_fill": "#1F2937",
    "section_text": "#FFFFFF",
    "subheader_fill": "#D1D5DB",
    "transparent": "#FFFFFF",
}


def _role(
    name: str,
    *,
    bold: bool = False,
    italic: bool = False,
    font_colour: str = PALETTE["primary_text"],
    fill_colour: str = PALETTE["transparent"],
    alignment: str = "left",
    wrap_text: bool = False,
    border_bottom: str = "none",
    locked: bool = True,
    font_size: int = 10,
) -> WorkbookStyleSpec:
    return WorkbookStyleSpec(
        format_role=name,
        font_family="Aptos",
        font_size=font_size,
        bold=bold,
        italic=italic,
        font_colour=font_colour,
        fill_colour=fill_colour,
        horizontal_alignment=alignment,
        wrap_text=wrap_text,
        border_bottom=border_bottom,
        locked=locked,
    )


STYLE_SPECS: dict[str, WorkbookStyleSpec] = {
    item.format_role: item
    for item in (
        _role(
            "control",
            bold=True,
            font_colour=PALETTE["control_text"],
            fill_colour=PALETTE["control_fill"],
            alignment="center",
            border_bottom="thin",
        ),
        _role(
            "header",
            bold=True,
            fill_colour=PALETTE["header_fill"],
            alignment="center",
            border_bottom="thin",
        ),
        _role(
            "input",
            font_colour=PALETTE["input_text"],
            fill_colour=PALETTE["input_fill"],
            alignment="right",
            locked=False,
        ),
        _role("label", wrap_text=True),
        _role("output", fill_colour=PALETTE["output_fill"], alignment="right"),
        _role(
            "period",
            bold=True,
            fill_colour=PALETTE["header_fill"],
            alignment="center",
            border_bottom="thin",
        ),
        _role("reference", italic=True, font_colour=PALETTE["reference_text"]),
        _role(
            "section_title",
            bold=True,
            font_colour=PALETTE["section_text"],
            fill_colour=PALETTE["section_fill"],
            border_bottom="thin",
            font_size=11,
        ),
        _role(
            "subheader",
            bold=True,
            fill_colour=PALETTE["subheader_fill"],
            border_bottom="thin",
        ),
    )
}

NUMBER_FORMAT_SPECS: dict[str, NumberFormatSpec] = {
    item.semantic_type: item
    for item in (
        NumberFormatSpec("boolean", "General"),
        NumberFormatSpec("currency", "#,##0;[Red](#,##0);-"),
        NumberFormatSpec("days", '0 "days"'),
        NumberFormatSpec("decimal", "0.0"),
        NumberFormatSpec("integer", "0"),
        NumberFormatSpec("multiple", "0.0x"),
        NumberFormatSpec("percentage", "0.0%;[Red](0.0%);-"),
        NumberFormatSpec("period", "0"),
        NumberFormatSpec("preserve_source", "source"),
        NumberFormatSpec("text", "General"),
        NumberFormatSpec("years", '0.0 "years"'),
    )
}

IDENTIFIER_SEMANTIC_TYPES: dict[str, str] = {
    "fmr.input.capital_expenditure_driver.v1": "currency",
    "fmr.input.covenant_threshold.v1": "multiple",
    "fmr.input.currency.v1": "text",
    "fmr.input.discount_rate.v1": "percentage",
    "fmr.input.fixed_cost_driver.v1": "currency",
    "fmr.input.forecast_horizon.v1": "integer",
    "fmr.input.growth_rate.v1": "percentage",
    "fmr.input.interest_rate.v1": "percentage",
    "fmr.input.inventory_days.v1": "days",
    "fmr.input.minimum_cash.v1": "currency",
    "fmr.input.new_interest_rate.v1": "percentage",
    "fmr.input.new_maturity.v1": "years",
    "fmr.input.opening_debt.v1": "currency",
    "fmr.input.payable_days.v1": "days",
    "fmr.input.price_driver.v1": "currency",
    "fmr.input.receivable_days.v1": "days",
    "fmr.input.refinancing_amount.v1": "currency",
    "fmr.input.scenario.v1": "text",
    "fmr.input.scheduled_repayment.v1": "currency",
    "fmr.input.sensitivity_axis_one.v1": "decimal",
    "fmr.input.sensitivity_axis_two.v1": "decimal",
    "fmr.input.sweep_percentage.v1": "percentage",
    "fmr.input.terminal_growth_rate.v1": "percentage",
    "fmr.input.useful_life.v1": "years",
    "fmr.input.variable_cost_driver.v1": "currency",
    "fmr.input.volume_driver.v1": "decimal",
}


def semantic_type_for_slot(slot: dict[str, Any], *, formula_output_type: str | None = None) -> str:
    kind = slot.get("content_kind")
    if kind == "label":
        return "text"
    if kind == "period_header":
        return "period"
    if kind == "reference_identifier":
        return "text"
    if kind == "validation_identifier":
        return "boolean"
    if kind == "formula_identifier":
        if formula_output_type is None:
            raise ValueError(f"formula output type is required for {slot.get('identifier')}")
        return formula_output_type
    identifier = slot.get("identifier")
    if kind == "input_placeholder" and isinstance(identifier, str):
        try:
            return IDENTIFIER_SEMANTIC_TYPES[identifier]
        except KeyError as exc:
            raise ValueError(f"missing input semantic type: {identifier}") from exc
    raise ValueError(f"unsupported content kind for style resolution: {kind}")


def style_spec_registry_payload() -> dict[str, Any]:
    _validate_registry()
    provisional = {
        "contract_version": "workbook-style-spec-registry.v1",
        "registry_version": "v1",
        "palette": dict(sorted(PALETTE.items())),
        "role_styles": [STYLE_SPECS[name].to_dict() for name in sorted(STYLE_SPECS)],
        "number_formats": [
            NUMBER_FORMAT_SPECS[name].to_dict() for name in sorted(NUMBER_FORMAT_SPECS)
        ],
        "identifier_semantic_types": dict(sorted(IDENTIFIER_SEMANTIC_TYPES.items())),
    }
    return {**provisional, "registry_sha256": _digest(provisional)}


def _validate_registry() -> None:
    required_roles = {
        slot.format_role for spec in CONTENT_SPECS.values() for slot in spec.slots
    }
    missing_roles = sorted(required_roles - set(STYLE_SPECS))
    if missing_roles:
        raise ValueError(f"style registry missing format roles: {missing_roles}")
    required_inputs = {
        slot.identifier
        for spec in CONTENT_SPECS.values()
        for slot in spec.slots
        if slot.content_kind == "input_placeholder" and slot.identifier is not None
    }
    missing_inputs = sorted(required_inputs - set(IDENTIFIER_SEMANTIC_TYPES))
    if missing_inputs:
        raise ValueError(f"style registry missing input semantic types: {missing_inputs}")
    for name, colour in PALETTE.items():
        if not _HEX_RE.fullmatch(colour):
            raise ValueError(f"invalid palette colour {name}: {colour}")
    for spec in STYLE_SPECS.values():
        if spec.horizontal_alignment not in _ALLOWED_ALIGNMENTS:
            raise ValueError(f"unsupported alignment: {spec.horizontal_alignment}")
        if spec.border_bottom not in _ALLOWED_BORDER_STYLES:
            raise ValueError(f"unsupported border style: {spec.border_bottom}")
        if not _HEX_RE.fullmatch(spec.font_colour) or not _HEX_RE.fullmatch(spec.fill_colour):
            raise ValueError(f"invalid style colour for role: {spec.format_role}")
        if spec.font_size < 8 or spec.font_size > 20:
            raise ValueError(f"unsupported font size for role: {spec.format_role}")
    if set(NUMBER_FORMAT_SPECS) != _ALLOWED_NUMBER_TYPES:
        raise ValueError("number format registry does not cover the required semantic types")
    for semantic_type in IDENTIFIER_SEMANTIC_TYPES.values():
        if semantic_type not in NUMBER_FORMAT_SPECS:
            raise ValueError(f"missing number format for semantic type: {semantic_type}")


def _digest(payload: Any) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()
