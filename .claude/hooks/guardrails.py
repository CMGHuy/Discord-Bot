"""PreToolUse guardrails -- enforce this repo's token rules at the moment of
the mistake rather than relying on CLAUDE.md having been recalled.

Rules encode what CLAUDE.md and .ignore already state. If a rule and
CLAUDE.md ever disagree, CLAUDE.md wins and the rule is what gets fixed.

Design: evaluate() reads no files and spawns no subprocesses -- os.path.getsize
and os.getcwd() are the only OS calls -- so the whole rule set is unit-tested in
tests/hooks/test_guardrails.py without a live session. Anything unrecognised
returns None -- silent allow. A guardrail that blocks legitimate work costs more
than the habit it prevents.
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

# A recursive grep: -r, -R (also recursive), or --recursive. Deliberately does
# NOT apply to rg, whose -r means --replace; rg recurses by default instead.
_GREP_RECURSIVE_RE = re.compile(
    r"(?:^|\s)(?:-[a-zA-Z]*[rR][a-zA-Z]*(?=\s|$)|--recursive(?=\s|$))"
)
# Where a positional-argument scan must stop: everything past a shell separator
# belongs to another command, not to this grep's target list.
_SHELL_SEPARATORS = {"|", "||", "&&", ";", "&", ">", ">>", "2>", "<"}
_ROOT_TARGETS = {".", "./", ".\\"}


def _is_repo_root_arg(value: str) -> bool:
    """True for the repo root spelled any of the usual ways, quotes included."""
    return value.strip().strip("\"'") in _ROOT_TARGETS


def _rule_unscoped_glob(ti: dict):
    path = ti.get("path")
    if path:
        # A path only counts as scoping when it names something below the root;
        # path="." is the very repo-root walk this rule exists to prevent.
        if not isinstance(path, str):
            return None
        if not _is_repo_root_arg(path):
            return None
    for key in GLOB_PATTERN_KEYS:
        pattern = ti.get(key)
        if isinstance(pattern, str) and pattern.startswith("**/"):
            return _deny(
                "Glob does not honour .ignore, so an unscoped pattern returns the three "
                ".claude/worktrees/ copies of this repo -- ~500 matches for 232 real files, "
                "and it points you at the wrong branch. Scope it by hand, e.g. "
                'Glob("swingbot/**/*.py"), or pass an explicit path=, e.g. path="swingbot" '
                '(path="." is the same repo-root walk and does not count).'
            )
    return None


def _rule_recursive_grep_from_root(ti: dict):
    cmd = ti.get("command")
    if not isinstance(cmd, str):
        return None
    args = cmd.strip().split()
    if not args:
        return None
    prog = args[0]
    if prog not in ("grep", "rg"):
        return None
    # grep needs an explicit recursion flag; rg recurses by default.
    if prog == "grep" and not _GREP_RECURSIVE_RE.search(" " + " ".join(args[1:])):
        return None
    targets = []
    for arg in args[1:]:
        if arg in _SHELL_SEPARATORS:
            break                       # the rest is a different command
        if not arg.startswith("-"):
            targets.append(arg)
    # Scoped to a real subdirectory is fine; only bare '.' or no path is not.
    if len(targets) >= 2 and not _is_repo_root_arg(targets[-1]):
        return None
    return _deny(
        "A recursive search from the repo root (`grep -r`/`-R`/`--recursive`, or `rg`, "
        "which recurses by default) does not respect .ignore -- it crawls ~2,600 files "
        "/ 160 MB including three worktree copies and times out at 20s returning "
        "nothing. Use the Grep tool (it honours .ignore) or `git grep -n` for tracked "
        "files only."
    )


_WORKTREE_SEGMENT_RE = re.compile(r"\.claude/worktrees/([^/]+)")
_CWD_UNKNOWN = object()


def _current_worktree_name():
    """Name of the worktree this process runs in, None for the main tree, or
    _CWD_UNKNOWN when the cwd cannot be read (never block on uncertainty)."""
    try:
        cwd = os.getcwd().replace("\\", "/")
    except OSError:
        return _CWD_UNKNOWN
    match = _WORKTREE_SEGMENT_RE.search(cwd)
    return match.group(1) if match else None


def _rule_worktree_write(ti: dict):
    path = ti.get("file_path")
    if not isinstance(path, str):
        return None
    match = _WORKTREE_SEGMENT_RE.search(path.replace("\\", "/"))
    if not match:
        return None                     # nothing to do with a worktree at all
    own = _current_worktree_name()
    if own is _CWD_UNKNOWN:
        return None                     # cannot tell which tree we are -- allow
    if own == match.group(1):
        return None                     # this session's own worktree: normal work
    return _deny(
        "That path belongs to a different tree than this session. Never edit files "
        "under .claude/worktrees/ from a main-tree session -- and the same holds "
        "across worktrees: the edit lands on another branch and is invisible here. "
        "Work in that worktree's own session instead."
    )


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
    "progress.md": "progress.md is 173 KB -- read only its tail (`tail` it, or Read "
                   "with an offset), never the whole file.",
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


def _rule_read_big_doc(ti: dict):
    """Read-side twin of _rule_cat_big_doc -- this harness tells agents to prefer
    Read over cat, so Read("README.md") is the likelier spelling of the mistake."""
    path = ti.get("file_path")
    if not isinstance(path, str):
        return None
    advice = _BIG_DOCS.get(os.path.basename(path.replace("\\", "/")))
    if advice is None:
        return None
    return _warn(advice + " Continuing anyway.")


# Rules run in list order; the first non-None decision wins. Warn rules are
# appended after deny rules on the same tool, so deny takes precedence.
_RULES = {
    "Glob": [_rule_unscoped_glob],
    "Bash": [_rule_recursive_grep_from_root, _rule_bare_pytest, _rule_cat_big_doc],
    "Read": [_rule_huge_implemented_plan, _rule_read_big_doc],
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
