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


# CLAUDE.md marks this a hard rule with no exceptions, and it was the only such
# rule with no mechanical enforcement at all before v96.
_BRANCH_DESTRUCTIVE_RE = re.compile(
    r"git\s+branch\s+(?:[^|;&]*\s)?(?:-[a-zA-Z]*[dD][a-zA-Z]*|--delete)(?=\s|$)"
    r"|git\s+push\s+[^|;&]*(?:--delete(?=\s|$)|\s:\S)"
    r"|git\s+push\s+[^|;&]*(?:--force(?:-with-lease)?|-f)(?=\s|$)"
    r"|git\s+update-ref\s+-d(?=\s|$)"
)
_PROTECTED_REF_RE = re.compile(r"backup|(?:^|[\s/:])stable-", re.IGNORECASE)


def _rule_protected_branch_delete(ti: dict):
    cmd = ti.get("command")
    if not isinstance(cmd, str):
        return None
    if not _BRANCH_DESTRUCTIVE_RE.search(cmd):
        return None
    if not _PROTECTED_REF_RE.search(cmd):
        return None
    return _deny(
        "Hard rule, no exceptions: a branch whose name contains `backup`, and any "
        "`stable-*` branch, is off limits to every destructive git command -- "
        "including force push. Run `git rev-list --count main..<branch>` first; "
        "non-zero means stop. Then ask the human partner. Do not decide this one. "
        "Evidence and the full checklist: docs/claude/git-safety.md."
    )


# Knobs whose pre-registration is closed (docs/claude/backtest-methodology.md,
# "Closed pre-registrations"). Deliberately NOT strategy names: the table closes
# mechanisms, and a strategy closed for one gate stays open for another.
# tests/hooks/test_guardrails.py asserts this list against the doc in both
# directions -- add a row there and the suite fails until this catches up.
CLOSED_PREREGISTRATION_KNOBS = frozenset({
    "REGIME_ALLOW",
    "REGIME_GATES_ENABLED",
    "DATA_DRIVEN_STOPS_ENABLED",
    "RS_GATE",
    "RS_LEADER_PERCENTILE",
    "RS_LAGGARD_PERCENTILE",
    "AVWAP_LEVELS_ENABLED",
    "LEVEL_TOUCH_STRENGTH",
    "EFFECTIVE_CONFLUENCE_ENABLED",
    "DEAD_CAT_BOUNCE_VETO",
    "EARNINGS_BLACKOUT_SESSIONS",
    "FIB_TARGET_1_0_EXTENSION",
    "COHORT_POOR",
    "STRATEGY_GATES",
    "VALIDATED",
    "STALL_EXIT_ENABLED",
    "ADAPTIVE_RUNNER_TRAIL_ENABLED",
    "TIGHTEN_TRIGGER_R",
    "TIGHTEN_ATR_MULT",
})
_BACKTEST_SCRIPT_RE = re.compile(r"(?:tune_strategy|run_backtest_range)\.py")


def _rule_closed_preregistration(ti: dict):
    cmd = ti.get("command")
    if not isinstance(cmd, str) or not _BACKTEST_SCRIPT_RE.search(cmd):
        return None
    hit = next((k for k in sorted(CLOSED_PREREGISTRATION_KNOBS) if k in cmd), None)
    if hit is None:
        return None
    return _deny(
        f"`{hit}` has a CLOSED pre-registration -- see the table in "
        "docs/claude/backtest-methodology.md. Re-running it does not produce a "
        "new result; it spends a shot the repo already spent and invites fitting "
        "the answer to the knob. A genuinely new mechanism over the same knob is "
        "a NEW pre-registration and needs its own spec. If this really is that, "
        "say so to the human partner and let them authorise it -- do not clear "
        "this yourself."
    )


# docs/superpowers/{specs,plans}/ have two unconditional shape rules
# (document-conventions.md): the vN-numbered filename, and `# Phase` with ONE
# hash so `grep -n "^# Phase"` can find it. v24 and v25 shipped with two and
# were invisible to the tool that exists to keep plans out of context.
_DOC_DIR_RE = re.compile(r"docs/superpowers/(?:specs|plans)/", re.IGNORECASE)
_DOC_NAME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}-v\d+-[a-z0-9][a-z0-9-]*"
    r"(?:_[0-9a-z]+(?:-[a-z0-9-]+)?)?\.md$"
)
_TWO_HASH_PHASE_RE = re.compile(r"^##\s+Phase\s", re.MULTILINE)
_ONE_HASH_PHASE_RE = re.compile(r"^#\s+Phase\s", re.MULTILINE)


def _rule_plan_doc_shape(ti: dict):
    path = ti.get("file_path")
    if not isinstance(path, str):
        return None
    norm = path.replace("\\", "/")
    if not _DOC_DIR_RE.search(norm):
        return None
    name = norm.rsplit("/", 1)[-1]
    if not _DOC_NAME_RE.match(name):
        return _deny(
            f"`{name}` does not match YYYY-MM-DD-vN-<name>.md. Every spec and plan "
            "is numbered at creation from one repo-wide counter, recomputed "
            "immediately before the commit. See docs/claude/document-conventions.md."
        )
    content = ti.get("content")
    if (
        isinstance(content, str)
        and _TWO_HASH_PHASE_RE.search(content)
        and not _ONE_HASH_PHASE_RE.search(content)
    ):
        return _deny(
            "`## Phase` uses two hashes. `CLAUDE.md` documents "
            '`grep -n "^# Phase"` as the way to orient in a plan, so a two-hash '
            "heading returns zero and the plan is invisible to the tooling that "
            "keeps it out of context. Use one hash, however wrong it looks beside "
            "the `##` sections around it. See docs/claude/document-conventions.md."
        )
    return None


# Rules run in list order; the first non-None decision wins. Warn rules are
# appended after deny rules on the same tool, so deny takes precedence.
_RULES = {
    "Glob": [_rule_unscoped_glob],
    "Bash": [_rule_protected_branch_delete, _rule_closed_preregistration,
             _rule_recursive_grep_from_root, _rule_bare_pytest, _rule_cat_big_doc],
    "Read": [_rule_huge_implemented_plan, _rule_read_big_doc],
    "Edit": [_rule_worktree_write],
    "Write": [_rule_worktree_write, _rule_plan_doc_shape],
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
