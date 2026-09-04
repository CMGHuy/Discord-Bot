"""Run pyflakes while reporting only undefined-name findings.

Pyflakes's CLI returns the same non-zero code for every diagnostic, including
the repository's deliberately out-of-scope unused-import debt. This reporter
filters at the source so exit 1 means an undefined name, exit 2 means the
checker could not inspect its inputs, and exit 0 is genuinely clean for this
gate.
"""
import sys

from pyflakes import messages
from pyflakes.api import checkPath
from pyflakes.reporter import Reporter


class _UndefinedNameReporter(Reporter):
    def __init__(self) -> None:
        super().__init__(sys.stdout, sys.stderr)
        self.findings = 0
        self.failed = False

    def flake(self, message) -> None:
        if isinstance(message, messages.UndefinedName):
            self.findings += 1
            super().flake(message)

    def unexpectedError(self, filename, msg) -> None:
        self.failed = True
        super().unexpectedError(filename, msg)

    def syntaxError(self, filename, msg, lineno, offset, text) -> None:
        self.failed = True
        super().syntaxError(filename, msg, lineno, offset, text)


def main(paths: list[str]) -> int:
    reporter = _UndefinedNameReporter()
    for path in paths:
        checkPath(path, reporter)
    if reporter.failed:
        return 2
    return 1 if reporter.findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
