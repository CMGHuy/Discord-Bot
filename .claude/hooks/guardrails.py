"""PreToolUse guardrails -- enforce this repo's token rules at the moment of
the mistake rather than relying on CLAUDE.md having been recalled.

Rules encode what CLAUDE.md and .ignore already state. If a rule and
CLAUDE.md ever disagree, CLAUDE.md wins and the rule is what gets fixed.

Design: evaluate() spawns no subprocesses. Its only file reads are the
idea-screen lookups (_screen_ledger_row reads the pre-registration ledger,
_screen_results_doc globs the results docs), and both go through module-level
constants (SCREEN_LEDGER_PATH, SCREEN_RESULTS_DIR) that tests point at
tmp_path. Otherwise os.path.getsize and os.getcwd() are the only OS calls, so
the whole rule set is unit-tested in tests/hooks/test_guardrails.py without a
live session. Anything unrecognised returns None -- silent allow, and a
missing or unreadable ledger reads as "no row". A guardrail that blocks
legitimate work costs more than the habit it prevents.
"""
import glob
import json
import os
import re
import shlex
import sys


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}


def _warn(message: str) -> dict:
    # additionalContext twice: inside hookSpecificOutput is the documented
    # PreToolUse spelling (the one Codex reads); the top-level key predates it.
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "additionalContext": message,
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
                 "docs/guides/setup.md, docs/guides/commands.md, docs/features/features.md.",
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
    "FVG_LEVELS_MODE",
    "PULLBACK_DRYUP_SCOPE",
    "PULLBACK_DRYUP_MAX_RATIO",
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


# The idea screen's one-shot rule (backtest-methodology.md "Funnel stages").
# screen_idea.py refuses a second real run of an id already in the ledger it
# is given; these helpers read a Bash command the way a shell would, so
# _rule_screen_rerun can close the ways round that refusal. The paths are
# module globals read at call time, so tests point them at tmp_path; the drift
# test pins SCREEN_LEDGER_PATH to stats.LEDGER_PATH because this hook stays
# stdlib-only and cannot import swingbot.
_HOOK_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCREEN_RESULTS_DIR = os.path.join(_HOOK_REPO_ROOT, "docs", "superpowers", "results")
SCREEN_LEDGER_PATH = os.path.join(SCREEN_RESULTS_DIR, "preregistration-ledger.jsonl")
_SCREEN_MAX_SMOKE_TICKERS = 3
_SCREEN_SEPARATORS = frozenset({"&&", "||", ";", "|", "&"})
_SCREEN_OPTIONS = ("--idea", "--cache-dir", "--membership", "--start", "--end",
                   "--date", "--ledger", "--results-dir", "--tickers", "--dry-run")
_SCREEN_VALUE_KEYS = {"--idea": "idea", "--ledger": "ledger",
                      "--results-dir": "results_dir"}


def _line_tokens(line: str) -> list[str] | None:
    """shlex tokens of one shell line, or None when it cannot be tokenised."""
    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return None


def _split_on_separators(tokens: list[str]) -> list[list[str]]:
    """`tokens` cut at every _SCREEN_SEPARATORS token; empty pieces dropped."""
    segments, current = [], []
    for tok in tokens:
        if tok in _SCREEN_SEPARATORS:
            segments.append(current)
            current = []
        else:
            current.append(tok)
    segments.append(current)
    return [seg for seg in segments if seg]


def _command_segments(cmd: str) -> list[list[str]] | None:
    """Shell segments of `cmd` as token lists, or None when a line that
    mentions screen_idea cannot be tokenised (any other such line is skipped)."""
    joined = cmd.replace("\\\r\n", " ").replace("\\\n", " ")
    segments = []
    for line in joined.splitlines():
        tokens = _line_tokens(line)
        if tokens is None:
            if "screen_idea" in line:
                return None
            continue
        segments.extend(_split_on_separators(tokens))
    return segments


def _is_screen_token(tok: str) -> bool:
    """The screen script as a path (any separator) or as a module name."""
    norm = tok.replace("\\", "/")
    return (norm.endswith("screen_idea.py") or norm == "screen_idea"
            or norm.endswith(".screen_idea"))


def _is_wrapped_screen(tok: str) -> bool:
    """A single token carrying a whole screen run: an ssh or pwsh wrapper."""
    return not _is_screen_token(tok) and "screen_idea" in tok and "--idea" in tok


def _resolve_screen_option(name: str) -> str | None:
    """`name` as argparse resolves it: exact, else a unique prefix."""
    if name in _SCREEN_OPTIONS:
        return name
    hits = [opt for opt in _SCREEN_OPTIONS if opt.startswith(name)]
    return hits[0] if len(hits) == 1 else None


def _screen_option_values(tokens: list[str]):
    """Yield (option, value) for each screen option in `tokens`; value is None
    for --dry-run and for an option with no value after it."""
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        i += 1
        name, eq, inline = tok.partition("=")
        opt = _resolve_screen_option(name) if name.startswith("--") else None
        if opt is None:
            continue
        if opt == "--dry-run" or eq:
            yield opt, (inline if eq else None)
        elif i < len(tokens) and not tokens[i].startswith("-"):
            yield opt, tokens[i]
            i += 1
        else:
            yield opt, None


def _screen_flags(tokens: list[str]) -> dict | None:
    """The screen flags of one segment, read after its first screen token;
    None when the segment does not run the screen."""
    start = next((i for i, tok in enumerate(tokens) if _is_screen_token(tok)), None)
    if start is None:
        return None
    flags = {"idea": None, "dry_run": False, "tickers": False, "ticker_count": 0,
             "ledger": None, "results_dir": None}
    for opt, value in _screen_option_values(tokens[start + 1:]):
        if opt == "--dry-run":
            flags["dry_run"] = True
        elif opt == "--tickers":
            flags["tickers"] = bool(value)
            flags["ticker_count"] = sum(
                1 for sym in (value or "").split(",") if sym.strip())
        elif opt in _SCREEN_VALUE_KEYS:
            flags[_SCREEN_VALUE_KEYS[opt]] = value
    return flags


def _same_repo_path(value: str, target: str) -> bool:
    """`value`, resolved against the repo root, names `target`."""
    resolved = os.path.join(_HOOK_REPO_ROOT, value)
    return (os.path.normcase(os.path.normpath(resolved))
            == os.path.normcase(os.path.normpath(target)))


def _is_default_ledger(value: str) -> bool:
    return _same_repo_path(value, SCREEN_LEDGER_PATH)


def _is_default_results_dir(value: str) -> bool:
    return _same_repo_path(value, SCREEN_RESULTS_DIR)


def _json_row(line: str) -> dict | None:
    try:
        row = json.loads(line)
    except ValueError:
        return None
    return row if isinstance(row, dict) else None


def _screen_ledger_row(idea: str) -> dict | None:
    """The ledger row whose id is exactly screen-<idea>, or None. A missing or
    unreadable ledger reads as no row; a malformed line is skipped."""
    want = f"screen-{idea}"
    try:
        with open(SCREEN_LEDGER_PATH, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return None
    for line in lines:
        row = _json_row(line)
        if row is not None and row.get("id") == want:
            return row
    return None


def _screen_results_doc(idea: str) -> str | None:
    """The first `*-screen-<idea>.md` in SCREEN_RESULTS_DIR, or None."""
    pattern = os.path.join(glob.escape(SCREEN_RESULTS_DIR),
                           f"*-screen-{glob.escape(idea)}.md")
    hits = sorted(glob.glob(pattern))
    return hits[0] if hits else None



_SCREEN_DENY_TAIL = (' -- one shot per idea; see docs/claude/backtest-methodology.md '
                     '"Funnel stages".')


def _screen_text(body: str) -> str:
    """A deny text in the one shape every _rule_screen_rerun denial shares."""
    return f"screen_idea: {body}{_SCREEN_DENY_TAIL}"


def _repo_relative(path: str) -> str:
    """`path` relative to the repo root with / separators, as the ledger's
    record field spells it; unchanged when it is on another drive."""
    try:
        return os.path.relpath(path, _HOOK_REPO_ROOT).replace("\\", "/")
    except ValueError:
        return path


def _screen_record_reason(idea: str) -> str | None:
    """The deny text when `idea` was already screened: its exact ledger row
    first, else a results doc a run left behind before it crashed."""
    row = _screen_ledger_row(idea)
    if row is not None:
        return _screen_text(
            f"screen-{idea} is already in the ledger ({row.get('date')}, "
            f"{row.get('verdict')}, {row.get('record')}); a second real run "
            "reads the same window again and is not a new result")
    doc = _screen_results_doc(idea)
    if doc is not None:
        return _screen_text(
            f"results doc {_repo_relative(doc)} exists with no ledger row; the "
            "run that wrote it spent the shot even though it stopped before the "
            "ledger append -- say so to the human partner, do not re-run")
    return None


def _screen_deny_reason(flags: dict) -> str | None:
    """The deny text for one screen segment, or None to allow it. The order is
    the index's Decision 10: a dry run is decided by --tickers alone; a real
    run is denied on a non-default ledger or results dir, then on a record."""
    if flags["dry_run"]:
        if flags["tickers"] and flags["ticker_count"] > _SCREEN_MAX_SMOKE_TICKERS:
            return _screen_text(
                f"--dry-run with more than {_SCREEN_MAX_SMOKE_TICKERS} --tickers "
                "re-reads the verdict across the universe and writes nothing; "
                "a smoke test names two or three symbols with --tickers")
        if flags["tickers"]:
            return None
        return _screen_text(
            "--dry-run without --tickers reads the whole universe and writes "
            "nothing; a smoke test names two or three symbols with --tickers")
    ledger, results_dir = flags["ledger"], flags["results_dir"]
    if ledger is not None and not _is_default_ledger(ledger):
        return _screen_text(
            f"--ledger other than the default ({ledger}) hides the rows of "
            "ideas already screened; a real run uses the default ledger")
    if results_dir is not None and not _is_default_results_dir(results_dir):
        return _screen_text(
            f"--results-dir other than the default ({results_dir}) hides the "
            "results docs of ideas already screened; a real run uses the "
            "default results dir")
    return _screen_record_reason(flags["idea"])


def _has_wrapped_screen(segments: list[list[str]]) -> bool:
    """Any token, in any segment, that carries a whole quoted screen run."""
    return any(_is_wrapped_screen(tok) for seg in segments for tok in seg)


def _rule_screen_rerun(ti: dict):
    """Deny a second run of a screened idea, a full-universe dry run, and the
    ways round screen_idea.py's own one-shot refusal (a fresh ledger or
    results dir, a quoted wrapper). Flags come only from the segment that
    runs the script, so `cd x && ...` and continuation lines read right."""
    cmd = ti.get("command")
    if not isinstance(cmd, str) or "screen_idea" not in cmd:
        return None
    segments = _command_segments(cmd)
    if segments is None:
        return _deny(_screen_text(
            "could not tokenise a line that mentions screen_idea (an unclosed "
            "quote?); write the command so a shell would read it"))
    if _has_wrapped_screen(segments):
        return _deny(_screen_text(
            "a screen run inside a quoted wrapper (ssh-hetzner.sh \"...\", "
            "pwsh -Command \"...\", a quoted commit message) is denied outright; "
            "the screen's cache lives on this machine, so run the script "
            "directly and name the rule, not the command line, in messages"))
    for seg in segments:
        flags = _screen_flags(seg)
        if flags is None or flags["idea"] is None:
            continue
        reason = _screen_deny_reason(flags)
        if reason is not None:
            return _deny(reason)
    return None


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


# Claude's setup is canonical and Codex runs a mirror of it (AGENTS.md,
# .agents/skills/, .codex/agents/, .codex/hooks.json). Every edit to the
# canonical side must land with its mirror in the same commit -- this reminder
# fires at the edit, where the step is cheapest to remember.
_CLAUDE_SETUP_RE = re.compile(
    r"(?:^|/)(?:CLAUDE\.md|docs/claude/[^/]+\.md|\.claude/skills/[^/]+/SKILL\.md"
    r"|\.claude/agents/[^/]+\.md|\.claude/hooks/[^/]+|\.claude/settings\.json)$"
)


def _rule_codex_mirror_reminder(ti: dict):
    path = ti.get("file_path")
    if not isinstance(path, str) or "/.claude/worktrees/" in path.replace("\\", "/"):
        return None
    if not _CLAUDE_SETUP_RE.search(path.replace("\\", "/")):
        return None
    return _warn(
        "This is Claude setup, which Codex mirrors. In the same commit: run "
        "`python scripts/dev/sync_codex.py` (regenerates .agents/skills/ and "
        ".codex/agents/), and update AGENTS.md (condensed) and .codex/hooks.json "
        "by hand if the rule, workflow or hook changed. "
        "See docs/claude/working-conventions.md, Codex mirror."
    )


# Codex edits files through apply_patch, whose tool_input.command is the patch
# text; the paths live in its `*** Add/Update/Delete File:` and `Move to:` lines.
_PATCH_PATH_RE = re.compile(
    r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", re.MULTILINE)
# Rule-major order: every path meets the deny rules before any path can warn.
_PATCH_PATH_RULES = (_rule_worktree_write, _rule_plan_doc_shape,
                     _rule_codex_mirror_reminder)


def _rule_apply_patch(ti: dict):
    patch = ti.get("command")
    if not isinstance(patch, str):
        return None
    paths = [p.strip() for p in _PATCH_PATH_RE.findall(patch)]
    for rule in _PATCH_PATH_RULES:
        for path in paths:
            decision = rule({"file_path": path})
            if decision is not None:
                return decision
    return None


# Rules run in list order; the first non-None decision wins. Warn rules are
# appended after deny rules on the same tool, so deny takes precedence.
# Codex (.codex/hooks.json) runs this same hook: its shell tool is `Bash` and
# its file edits arrive as `apply_patch`, `Edit` or `Write`.
_RULES = {
    "Glob": [_rule_unscoped_glob],
    "Bash": [_rule_protected_branch_delete, _rule_closed_preregistration,
             _rule_screen_rerun, _rule_recursive_grep_from_root,
             _rule_bare_pytest, _rule_cat_big_doc],
    "Read": [_rule_huge_implemented_plan, _rule_read_big_doc],
    "Edit": [_rule_worktree_write, _rule_codex_mirror_reminder],
    "Write": [_rule_worktree_write, _rule_plan_doc_shape, _rule_codex_mirror_reminder],
    "NotebookEdit": [_rule_worktree_write],
    "apply_patch": [_rule_apply_patch],
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
