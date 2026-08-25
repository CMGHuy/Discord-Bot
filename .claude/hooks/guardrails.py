"""PreToolUse guardrails -- enforce this repo's token rules at the moment of
the mistake rather than relying on CLAUDE.md having been recalled.

Rules encode what CLAUDE.md and .ignore already state. If a rule and
CLAUDE.md ever disagree, CLAUDE.md wins and the rule is what gets fixed.

Design: evaluate() is pure and does no I/O beyond os.path.getsize, so the
whole rule set is unit-tested in tests/hooks/test_guardrails.py without a
live session. Anything unrecognised returns None -- silent allow. A
guardrail that blocks legitimate work costs more than the habit it prevents.
"""
import json
import os
import re
import sys


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}


def _warn(message: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
    }, "additionalContext": message}


GLOB_PATTERN_KEYS = ("pattern", "glob")
_IMPLEMENTED_PLAN_MAX_BYTES = 100_000
_GREP_ROOT_RE = re.compile(r"^\s*(grep|rg)\b(?=.*\s-\w*r)")


def _rule_unscoped_glob(ti: dict):
    if ti.get("path"):
        return None
    for key in GLOB_PATTERN_KEYS:
        pattern = ti.get(key)
        if isinstance(pattern, str) and pattern.startswith("**/"):
            return _deny(
                "Glob does not honour .ignore, so an unscoped pattern returns the three "
                ".claude/worktrees/ copies of this repo -- ~500 matches for 232 real files, "
                "and it points you at the wrong branch. Scope it by hand, e.g. "
                'Glob("swingbot/**/*.py"), or pass path=.'
            )
    return None


def _rule_recursive_grep_from_root(ti: dict):
    cmd = ti.get("command")
    if not isinstance(cmd, str) or not _GREP_ROOT_RE.match(cmd):
        return None
    # Scoped to a real subdirectory is fine; only bare '.' or no path is not.
    tail = cmd.split()
    targets = [a for a in tail[1:] if not a.startswith("-")]
    if len(targets) >= 2 and targets[-1] not in (".", "./"):
        return None
    return _deny(
        "Plain `grep -r` from the repo root does not respect .ignore -- it crawls "
        "~2,600 files / 160 MB including three worktree copies and times out at 20s "
        "returning nothing. Use the Grep tool (it honours .ignore) or `git grep -n` "
        "for tracked files only."
    )


def _rule_worktree_write(ti: dict):
    path = ti.get("file_path")
    if isinstance(path, str) and ".claude/worktrees/" in path.replace("\\", "/"):
        return _deny(
            "Never edit files under .claude/worktrees/ from a main-tree session -- "
            "that edits a different branch and the change is invisible here. Work in "
            "that worktree's own session instead."
        )
    return None


def _rule_huge_implemented_plan(ti: dict):
    path = ti.get("file_path")
    if not isinstance(path, str):
        return None
    if "implemented" not in path.replace("\\", "/"):
        return None
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    if size <= _IMPLEMENTED_PLAN_MAX_BYTES:
        return None
    return _deny(
        f"That file is {size // 1024} KB (~{size // 4 // 1000}K tokens) and reading it "
        "whole would consume a large share of this session. Pull the one task instead: "
        '/task-brief <id>, or grep -n "^### Task <id>" -A 120 <plan>. '
        'Use grep -c "^### Task" to orient first.'
    )


# Populated (Tasks 3-4 rules registered below): tool name -> list of rule callables.
# Each rule takes tool_input (dict) and returns a decision dict or None.
_BARE_PYTEST_RE = re.compile(r"python\s+-m\s+pytest\s*(-\w+\s*)*$")
_BIG_DOCS = {
    "README.md": "README.md is a short overview + documentation index. Read the "
                 "topic file it points at instead -- docs/strategy/strategy.md, "
                 "docs/setup.md, docs/commands.md, docs/features/features.md.",
    "progress.md": "progress.md is 173 KB. tail it, never cat it.",
}


def _rule_bare_pytest(ti: dict):
    cmd = ti.get("command")
    if not isinstance(cmd, str) or not _BARE_PYTEST_RE.search(cmd.strip()):
        return None
    return _warn(
        "A bare `python -m pytest` puts ~1150 progress lines into context. "
        "`python scripts/dev/testrun.py fast` is ~27s and prints a one-line verdict; "
        "`... file tests/test_foo.py` is ~7s. For a full run, dispatch the test-runner "
        "subagent so none of the output reaches this context. Continuing anyway."
    )


def _rule_cat_big_doc(ti: dict):
    cmd = ti.get("command")
    if not isinstance(cmd, str) or not cmd.strip().startswith("cat "):
        return None
    for name, advice in _BIG_DOCS.items():
        if name in cmd:
            return _warn(advice + " Continuing anyway.")
    return None


# Rules run in list order; the first non-None decision wins. Warn rules are
# appended after deny rules on the same tool, so deny takes precedence.
_RULES = {
    "Glob": [_rule_unscoped_glob],
    "Bash": [_rule_recursive_grep_from_root, _rule_bare_pytest, _rule_cat_big_doc],
    "Read": [_rule_huge_implemented_plan],
    "Edit": [_rule_worktree_write],
    "Write": [_rule_worktree_write],
    "NotebookEdit": [_rule_worktree_write],
}


def evaluate(payload: dict):
    """Return the JSON to emit, or None for a silent allow."""
    try:
        tool = payload.get("tool_name")
        tool_input = payload.get("tool_input")
        if not tool or not isinstance(tool_input, dict):
            return None
        for rule in _RULES.get(tool, ()):
            decision = rule(tool_input)
            if decision is not None:
                return decision
        return None
    except Exception:
        return None      # fail open, always


def main() -> int:
    try:
        decision = evaluate(json.load(sys.stdin))
        if decision is not None:
            print(json.dumps(decision))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
