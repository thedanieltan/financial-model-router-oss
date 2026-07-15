from __future__ import annotations

import re
from typing import Any

from fmr.core import create_model_intent, validate_model_intent
from fmr.core.handoffs import digest
from fmr.providers.native_xlsx.workbook.evidence import derive_workbook_evidence
from fmr.providers.native_xlsx.workbook.types import WorkbookMap


_HEX_64 = re.compile(r"[a-f0-9]{64}")
_CONFIDENCE = {"medium", "high"}
_KINDS = {"available_data", "workbook_capability"}
_STANDARD_LIMITATION = "Workbook structure cannot establish user intent or assumptions."


def _workbook_map(value: WorkbookMap | dict[str, Any]) -> WorkbookMap:
    return value if isinstance(value, WorkbookMap) else WorkbookMap.from_mapping(value)


def derive_workbook_scope_evidence(workbook_map: WorkbookMap | dict[str, Any]) -> dict[str, Any]:
    canonical = _workbook_map(workbook_map)
    evidence = derive_workbook_evidence(canonical)
    observations = sorted(
        (item.to_dict() for item in evidence.items),
        key=lambda item: (item["kind"], item["value"]),
    )
    warnings = []
    if canonical.external_links_detected:
        warnings.append("external workbook links were detected")
    provisional = {
        "contract_version": "model-scope-workbook-evidence.v1",
        "source": {
            "contract_version": "workbook-map.v1",
            "filename": canonical.source_filename,
            "sha256": canonical.source_sha256.lower(),
            "size_bytes": canonical.source_size_bytes,
            "workbook_map_sha256": digest(canonical.to_dict()),
        },
        "observed_data": sorted(evidence.available_data),
        "observed_capabilities": sorted(evidence.workbook_capabilities),
        "observations": observations,
        "warnings": sorted(warnings),
        "limitations": sorted(set((*canonical.limitations, _STANDARD_LIMITATION))),
    }
    sha = digest(provisional)
    return {
        **provisional,
        "evidence_id": f"fmrwe_{sha[:24]}",
        "evidence_sha256": sha,
    }


def validate_workbook_scope_evidence(value: Any) -> tuple[str, ...]:
    if not isinstance(value, dict) or value.get("contract_version") != "model-scope-workbook-evidence.v1":
        return ("unsupported workbook scope evidence contract",)
    expected = {
        "contract_version", "evidence_id", "evidence_sha256", "source",
        "observed_data", "observed_capabilities", "observations", "warnings",
        "limitations",
    }
    issues: list[str] = []
    if set(value) != expected:
        issues.append("workbook scope evidence fields do not match the contract")
    source = value.get("source")
    source_expected = {"contract_version", "filename", "sha256", "size_bytes", "workbook_map_sha256"}
    if not isinstance(source, dict) or set(source) != source_expected:
        issues.append("workbook scope evidence source fields do not match the contract")
    else:
        if source.get("contract_version") != "workbook-map.v1":
            issues.append("workbook scope evidence source contract is unsupported")
        if not isinstance(source.get("filename"), str) or not source["filename"]:
            issues.append("workbook scope evidence source filename is required")
        if not isinstance(source.get("size_bytes"), int) or isinstance(source.get("size_bytes"), bool) or source["size_bytes"] < 0:
            issues.append("workbook scope evidence source size is invalid")
        for field in ("sha256", "workbook_map_sha256"):
            if not isinstance(source.get(field), str) or not _HEX_64.fullmatch(source[field]):
                issues.append(f"workbook scope evidence source {field} is invalid")
    for field in ("observed_data", "observed_capabilities", "warnings", "limitations"):
        items = value.get(field)
        if not isinstance(items, list) or not all(isinstance(item, str) and item for item in items):
            issues.append(f"workbook scope evidence {field} must be an array of non-empty strings")
        elif items != sorted(set(items)):
            issues.append(f"workbook scope evidence {field} must be sorted and unique")
    observations = value.get("observations")
    if not isinstance(observations, list):
        issues.append("workbook scope evidence observations must be an array")
    else:
        for observation in observations:
            if not isinstance(observation, dict) or set(observation) != {"kind", "value", "confidence", "evidence"}:
                issues.append("workbook scope evidence observation fields do not match the contract")
                continue
            if observation.get("kind") not in _KINDS:
                issues.append("workbook scope evidence observation kind is invalid")
            if not isinstance(observation.get("value"), str) or not observation["value"]:
                issues.append("workbook scope evidence observation value is required")
            if observation.get("confidence") not in _CONFIDENCE:
                issues.append("workbook scope evidence observation confidence is invalid")
            details = observation.get("evidence")
            if not isinstance(details, list) or not details or not all(isinstance(item, str) and item for item in details):
                issues.append("workbook scope evidence observation evidence is required")
        if observations != sorted(observations, key=lambda item: (item.get("kind", ""), item.get("value", "")) if isinstance(item, dict) else ("", "")):
            issues.append("workbook scope evidence observations must be deterministically ordered")
        valid_observations = [item for item in observations if isinstance(item, dict)]
        observed_data = sorted(item.get("value") for item in valid_observations if item.get("kind") == "available_data" and isinstance(item.get("value"), str))
        observed_capabilities = sorted(item.get("value") for item in valid_observations if item.get("kind") == "workbook_capability" and isinstance(item.get("value"), str))
        if value.get("observed_data") != observed_data:
            issues.append("workbook scope evidence observed_data does not match observations")
        if value.get("observed_capabilities") != observed_capabilities:
            issues.append("workbook scope evidence observed_capabilities does not match observations")
    if isinstance(value.get("limitations"), list) and _STANDARD_LIMITATION not in value["limitations"]:
        issues.append("workbook scope evidence intent limitation is required")
    provisional = {key: item for key, item in value.items() if key not in {"evidence_id", "evidence_sha256"}}
    sha = digest(provisional)
    if value.get("evidence_sha256") != sha or value.get("evidence_id") != f"fmrwe_{sha[:24]}":
        issues.append("workbook scope evidence identity does not match canonical payload")
    return tuple(dict.fromkeys(issues))


def apply_workbook_scope_evidence(
    intent: dict[str, Any],
    evidence: dict[str, Any],
    *,
    workbook_map: WorkbookMap | dict[str, Any],
) -> dict[str, Any]:
    intent_issues = validate_model_intent(intent)
    if intent_issues:
        raise ValueError("invalid model intent: " + "; ".join(intent_issues))
    evidence_issues = validate_workbook_scope_evidence(evidence)
    if evidence_issues:
        raise ValueError("invalid workbook scope evidence: " + "; ".join(evidence_issues))
    expected = derive_workbook_scope_evidence(workbook_map)
    if evidence != expected:
        raise ValueError("workbook scope evidence does not match deterministic recomputation")
    raw = {
        key: value
        for key, value in intent.items()
        if key not in {"contract_version", "intent_id", "intent_sha256"}
    }
    existing_model = dict(raw["existing_model"])
    if "workbook_scope_evidence" in existing_model:
        raise ValueError("model intent already contains workbook scope evidence")
    existing_model["workbook_scope_evidence"] = {
        "contract_version": evidence["contract_version"],
        "evidence_id": evidence["evidence_id"],
        "evidence_sha256": evidence["evidence_sha256"],
        "source_sha256": evidence["source"]["sha256"],
    }
    raw["existing_model"] = existing_model
    raw["available_data"] = sorted(set((*raw["available_data"], *evidence["observed_data"])))
    context = dict(raw["context"])
    explicit_capabilities = context.get("workbook_capabilities", [])
    if not isinstance(explicit_capabilities, list) or not all(isinstance(item, str) and item for item in explicit_capabilities):
        raise ValueError("model intent context.workbook_capabilities must be an array of non-empty strings")
    context["workbook_capabilities"] = sorted(set((*explicit_capabilities, *evidence["observed_capabilities"])))
    raw["context"] = context
    return create_model_intent(raw)
