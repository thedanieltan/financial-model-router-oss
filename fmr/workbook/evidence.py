from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from fmr.workbook.types import WorkbookMap

_ACCEPTED_CONFIDENCE = {"medium", "high"}
_ROLE_DATA = {
    "income_statement": "income_statement_history",
    "balance_sheet": "balance_sheet_history",
    "cash_flow_statement": "cash_flow_history",
    "debt_schedule": "debt_schedule",
}
_FORECAST_RE = re.compile(
    r"(?:\b(?:budget|forecast|estimate|ntm)\b|(?:19|20)\d{2}\s*(?:e|f)\b)",
    re.IGNORECASE,
)
_HISTORICAL_RE = re.compile(
    r"(?:\bactual\b|\bltm\b|(?:19|20)\d{2}\s*(?:a)?\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EvidenceItem:
    kind: str
    value: str
    confidence: str
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class WorkbookEvidence:
    available_data: tuple[str, ...]
    workbook_capabilities: tuple[str, ...]
    items: tuple[EvidenceItem, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "available_data": list(self.available_data),
            "workbook_capabilities": list(self.workbook_capabilities),
            "items": [item.to_dict() for item in self.items],
        }


def derive_workbook_evidence(workbook_map: WorkbookMap) -> WorkbookEvidence:
    items: list[EvidenceItem] = []
    historical_sheets: list[str] = []
    forecast_sheets: list[str] = []

    for sheet in workbook_map.sheets:
        historical_periods = tuple(
            period for period in sheet.detected_periods if _is_historical(period)
        )
        forecast_periods = tuple(
            period for period in sheet.detected_periods if _is_forecast(period)
        )
        role = sheet.candidate_role.value
        accepted_role = (
            role != "unknown"
            and sheet.candidate_role.confidence in _ACCEPTED_CONFIDENCE
        )
        if accepted_role and len(historical_periods) >= 2:
            historical_sheets.append(sheet.name)
        if accepted_role and forecast_periods:
            forecast_sheets.append(sheet.name)

        if (
            role in _ROLE_DATA
            and accepted_role
            and len(historical_periods) >= 2
            and sheet.formula_cells + sheet.value_cells > 0
        ):
            items.append(
                EvidenceItem(
                    kind="available_data",
                    value=_ROLE_DATA[role],
                    confidence=sheet.candidate_role.confidence,
                    evidence=(
                        f"sheet:{sheet.name}",
                        f"role:{role}",
                        f"historical_periods:{','.join(historical_periods)}",
                        *sheet.candidate_role.evidence,
                    ),
                )
            )

        if (
            role == "assumptions"
            and accepted_role
            and sheet.formula_cells + sheet.value_cells > 0
        ):
            items.append(
                EvidenceItem(
                    kind="workbook_capability",
                    value="assumptions_section",
                    confidence=sheet.candidate_role.confidence,
                    evidence=(f"sheet:{sheet.name}", *sheet.candidate_role.evidence),
                )
            )

        if (
            role == "balance_sheet"
            and accepted_role
            and {"cash", "debt"}.issubset(set(sheet.candidate_metrics))
            and historical_periods
        ):
            items.append(
                EvidenceItem(
                    kind="available_data",
                    value="net_debt",
                    confidence=sheet.candidate_role.confidence,
                    evidence=(
                        f"sheet:{sheet.name}",
                        "metrics:cash,debt",
                        f"periods:{','.join(historical_periods)}",
                    ),
                )
            )

    if historical_sheets:
        items.append(
            EvidenceItem(
                kind="workbook_capability",
                value="historical_periods",
                confidence="high",
                evidence=tuple(f"sheet:{name}" for name in historical_sheets),
            )
        )
    if forecast_sheets:
        items.append(
            EvidenceItem(
                kind="workbook_capability",
                value="forecast_periods",
                confidence="high",
                evidence=tuple(f"sheet:{name}" for name in forecast_sheets),
            )
        )
    formula_sheets = [sheet.name for sheet in workbook_map.sheets if sheet.formula_cells]
    if formula_sheets:
        items.append(
            EvidenceItem(
                kind="workbook_capability",
                value="existing_formulas",
                confidence="high",
                evidence=tuple(f"sheet:{name}" for name in formula_sheets),
            )
        )

    deduplicated: dict[tuple[str, str], EvidenceItem] = {}
    for item in items:
        key = (item.kind, item.value)
        existing = deduplicated.get(key)
        if existing is None:
            deduplicated[key] = item
        else:
            merged = tuple(dict.fromkeys(existing.evidence + item.evidence))
            confidence = (
                "high"
                if "high" in {existing.confidence, item.confidence}
                else "medium"
            )
            deduplicated[key] = EvidenceItem(
                item.kind,
                item.value,
                confidence,
                merged,
            )

    ordered = tuple(
        sorted(deduplicated.values(), key=lambda item: (item.kind, item.value))
    )
    return WorkbookEvidence(
        available_data=tuple(
            item.value for item in ordered if item.kind == "available_data"
        ),
        workbook_capabilities=tuple(
            item.value for item in ordered if item.kind == "workbook_capability"
        ),
        items=ordered,
    )


def _is_forecast(period: str) -> bool:
    return bool(_FORECAST_RE.search(period.strip()))


def _is_historical(period: str) -> bool:
    text = period.strip()
    return bool(_HISTORICAL_RE.search(text)) and not _is_forecast(text)
