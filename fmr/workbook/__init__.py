"""Deterministic XLSX inspection, analysis and non-mutating workbook planning."""

from fmr.workbook.analyse import WorkbookAnalysis, analyse_workbook_map
from fmr.workbook.content_plan import (
    plan_workbook_content,
    validate_workbook_content_plan_payload,
)
from fmr.workbook.content_specs import (
    CONTENT_SPECS,
    ContentSlotSpec,
    WorkbookContentSpec,
    content_spec_registry_payload,
)
from fmr.workbook.coordinate_plan import (
    Rectangle,
    plan_workbook_coordinates,
    validate_workbook_coordinate_plan_payload,
)
from fmr.workbook.coordinate_rules import (
    COORDINATE_RULES,
    WorkbookCoordinateRule,
    coordinate_rule_registry_payload,
)
from fmr.workbook.evidence import EvidenceItem, WorkbookEvidence, derive_workbook_evidence
from fmr.workbook.formula_specs import (
    FORMULA_SPECS,
    FormulaDependency,
    WorkbookFormulaSpec,
    formula_spec_registry_payload,
    resolve_formula_spec,
)
from fmr.workbook.inspect import inspect_workbook, inspect_workbook_bytes
from fmr.workbook.operation_specs import (
    OPERATION_SPECS,
    WorkbookOperationSpec,
    operation_spec_registry_payload,
)
from fmr.workbook.patch import (
    PatchCheck,
    PatchOperation,
    WorkbookPatch,
    compile_workbook_patch,
)
from fmr.workbook.patch_validation import (
    validate_workbook_patch_payload,
    validate_workbook_patch_receipt_payload,
)
from fmr.workbook.realization_plan import plan_workbook_realization
from fmr.workbook.realization_validation import (
    validate_workbook_realization_plan_payload,
)
from fmr.workbook.style_specs import (
    IDENTIFIER_SEMANTIC_TYPES,
    NUMBER_FORMAT_SPECS,
    PALETTE,
    STYLE_SPECS,
    NumberFormatSpec,
    WorkbookStyleSpec,
    semantic_type_for_slot,
    style_spec_registry_payload,
)
from fmr.workbook.target_resolution import (
    OperationTargetResolution,
    ResolutionAnchor,
    WorkbookTargetResolution,
    resolve_workbook_patch_targets,
    validate_workbook_target_resolution_payload,
)
from fmr.workbook.types import Classification, SheetMap, WorkbookMap
from fmr.workbook.write_plan_public import (
    compile_workbook_write_plan,
    validate_workbook_write_context_payload,
    validate_workbook_write_plan_payload,
)

__all__ = [
    "CONTENT_SPECS",
    "COORDINATE_RULES",
    "FORMULA_SPECS",
    "IDENTIFIER_SEMANTIC_TYPES",
    "NUMBER_FORMAT_SPECS",
    "OPERATION_SPECS",
    "PALETTE",
    "STYLE_SPECS",
    "Classification",
    "ContentSlotSpec",
    "EvidenceItem",
    "FormulaDependency",
    "NumberFormatSpec",
    "OperationTargetResolution",
    "PatchCheck",
    "PatchOperation",
    "Rectangle",
    "ResolutionAnchor",
    "SheetMap",
    "WorkbookAnalysis",
    "WorkbookContentSpec",
    "WorkbookCoordinateRule",
    "WorkbookEvidence",
    "WorkbookFormulaSpec",
    "WorkbookMap",
    "WorkbookOperationSpec",
    "WorkbookPatch",
    "WorkbookStyleSpec",
    "WorkbookTargetResolution",
    "analyse_workbook_map",
    "compile_workbook_patch",
    "compile_workbook_write_plan",
    "content_spec_registry_payload",
    "coordinate_rule_registry_payload",
    "derive_workbook_evidence",
    "formula_spec_registry_payload",
    "inspect_workbook",
    "inspect_workbook_bytes",
    "operation_spec_registry_payload",
    "plan_workbook_content",
    "plan_workbook_coordinates",
    "plan_workbook_realization",
    "resolve_formula_spec",
    "resolve_workbook_patch_targets",
    "semantic_type_for_slot",
    "style_spec_registry_payload",
    "validate_workbook_content_plan_payload",
    "validate_workbook_coordinate_plan_payload",
    "validate_workbook_patch_payload",
    "validate_workbook_patch_receipt_payload",
    "validate_workbook_realization_plan_payload",
    "validate_workbook_target_resolution_payload",
    "validate_workbook_write_context_payload",
    "validate_workbook_write_plan_payload",
]
