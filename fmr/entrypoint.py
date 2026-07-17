from __future__ import annotations

import sys

from fmr.dispatch import main as dispatch_main
from fmr.financial_data_dispatch import (
    FINANCIAL_DATA_COMMANDS,
    run_financial_data_command,
)
from fmr.input_dispatch import INPUT_COMMANDS, run_input_command
from fmr.provider_dispatch import PROVIDER_COMMANDS, run_provider_command
from fmr.workflow_dispatch import WORKFLOW_COMMANDS, run_workflow_command


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in WORKFLOW_COMMANDS:
        return run_workflow_command(arguments)
    if arguments and arguments[0] in PROVIDER_COMMANDS:
        return run_provider_command(arguments)
    if arguments and arguments[0] in FINANCIAL_DATA_COMMANDS:
        return run_financial_data_command(arguments)
    if arguments and arguments[0] in INPUT_COMMANDS:
        return run_input_command(arguments)
    return dispatch_main(arguments)


__all__ = ["main"]
