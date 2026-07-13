from __future__ import annotations

import sys

from fmr.dispatch import main as dispatch_main
from fmr.input_dispatch import INPUT_COMMANDS, run_input_command


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in INPUT_COMMANDS:
        return run_input_command(arguments)
    return dispatch_main(arguments)


__all__ = ["main"]
