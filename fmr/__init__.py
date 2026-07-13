"""Financial Model Router public API."""

from fmr.plan import build_plan
from fmr.router import route_request
from fmr.workbook import (
    analyse_workbook_map,
    compile_workbook_patch,
    content_spec_registry_payload,
    coordinate_rule_registry_payload,
    derive_workbook_evidence,
    inspect_workbook,
    inspect_workbook_bytes,
    operation_spec_registry_payload,
    plan_workbook_content,
    plan_workbook_coordinates,
    resolve_workbook_patch_targets,
    validate_workbook_content_plan_payload,
    validate_workbook_coordinate_plan_payload,
    validate_workbook_patch_payload,
    validate_workbook_patch_receipt_payload,
    validate_workbook_target_resolution_payload,
)

__all__ = [
    "analyse_workbook_map",
    "build_plan",
    "compile_workbook_patch",
    "content_spec_registry_payload",
    "coordinate_rule_registry_payload",
    "derive_workbook_evidence",
    "inspect_workbook",
    "inspect_workbook_bytes",
    "operation_spec_registry_payload",
    "plan_workbook_content",
    "plan_workbook_coordinates",
    "resolve_workbook_patch_targets",
    "route_request",
    "validate_workbook_content_plan_payload",
    "validate_workbook_coordinate_plan_payload",
    "validate_workbook_patch_payload",
    "validate_workbook_patch_receipt_payload",
    "validate_workbook_target_resolution_payload",
]
__version__ = "0.3.3"
