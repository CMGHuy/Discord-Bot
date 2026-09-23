"""Guards CI's testrun.py invocations against argparse ordering footguns.

deploy.yml shipped broken 2026-09-23: every backend-test-* shard ran
`testrun.py full --skip-lint-gate <paths>`, which argparse silently refuses
-- a `--flag` sandwiched between the `profile` positional and a `nargs='*'`
target is not consumed the same way as one placed after the target list (see
testrun.py's build_parser() docstring). No local test caught it because the
only coverage was hand-picked argv, never the literal strings the workflow
actually runs. This extracts every real `testrun.py` command from deploy.yml
and parses it for real, so an edit that reintroduces a bad order fails here
instead of only in CI.
"""
import re
import shlex
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "dev"))

WORKFLOW = REPO / ".github" / "workflows" / "deploy.yml"

# Matches one `python scripts/dev/testrun.py ...` invocation. Applied AFTER
# backslash-newline continuations are joined, so a multi-line `run: |` block
# reads as one line, the same as the shell that actually executes it sees it.
_INVOCATION_RE = re.compile(r"python scripts/dev/testrun\.py[ \t]+(.+)")


def _extract_invocations() -> list[str]:
    text = WORKFLOW.read_text(encoding="utf-8")
    joined = re.sub(r"\\\r?\n[ \t]*", " ", text)
    return [m.group(1).strip() for m in _INVOCATION_RE.finditer(joined)]


def test_deploy_workflow_has_testrun_invocations():
    # A regex that stopped matching would make every check below vacuously
    # pass without testing anything -- assert there is something to check.
    assert len(_extract_invocations()) >= 5


@pytest.mark.parametrize("line", _extract_invocations())
def test_every_ci_testrun_invocation_parses(line):
    import testrun

    argv = shlex.split(line)
    try:
        testrun.build_parser().parse_args(argv)
    except SystemExit as exc:
        pytest.fail(f"testrun.py {line!r} fails to parse (argparse exited: {exc})")
