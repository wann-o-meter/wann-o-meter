"""Harvest pipeline CLI skeleton (see the harvest-pipeline spec's Stage
1-7). Only `registry` is implemented so far; each later stage (discover,
extract, validate, publish, run) gets its own entry in COMMANDS once it
exists, the same fetch -> extract -> validate -> publish shape as
core/runner.py.

    cd pipeline && uv run python -m harvest.cli registry university_de
"""

import sys

from harvest import registry


def _registry_command(args: list) -> int:
    if not args:
        print("[harvest] Usage: harvest registry <entity_class>", file=sys.stderr)
        return 2
    return registry.run(args[0])


COMMANDS = {"registry": _registry_command}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in COMMANDS:
        print(f"[harvest] Usage: harvest <stage> [args...]. Known stages: {', '.join(COMMANDS)}", file=sys.stderr)
        return 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
