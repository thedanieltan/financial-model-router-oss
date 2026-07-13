from fmr.types import ModelDefinition, ModelRequest, ReadinessReport


def assess_readiness(request: ModelRequest, definition: ModelDefinition) -> ReadinessReport:
    data = set(request.available_data)
    assumptions = set(request.assumptions)
    capabilities = set(request.workbook_capabilities)
    missing_data = tuple(sorted(set(definition.required_data) - data))
    missing_assumptions = tuple(sorted(set(definition.required_assumptions) - assumptions))
    missing_capabilities = tuple(sorted(set(definition.required_workbook_capabilities) - capabilities))
    blockers = tuple([f"missing_data:{item}" for item in missing_data] + [f"missing_assumption:{item}" for item in missing_assumptions] + [f"missing_workbook_capability:{item}" for item in missing_capabilities])
    return ReadinessReport(
        ready=not blockers,
        available_data=tuple(sorted(data.intersection(definition.required_data))),
        missing_data=missing_data,
        available_assumptions=tuple(sorted(assumptions.intersection(definition.required_assumptions))),
        missing_assumptions=missing_assumptions,
        available_workbook_capabilities=tuple(sorted(capabilities.intersection(definition.required_workbook_capabilities))),
        missing_workbook_capabilities=missing_capabilities,
        blockers=blockers,
    )
