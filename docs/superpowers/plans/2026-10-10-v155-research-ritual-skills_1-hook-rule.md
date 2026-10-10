# v155 Research ritual skills: Implementation Plan, part 1 -- screen re-run hook rule

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `/task-brief V155-1` or `grep -n "^### Task V155-1" -A 400 <this file>`.

**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-10-v155-research-ritual-skills-design.md`](../specs/2026-10-10-v155-research-ritual-skills-design.md)
**Index:** [`2026-10-10-v155-research-ritual-skills_0-index.md`](2026-10-10-v155-research-ritual-skills_0-index.md) -- Global Constraints, Decisions, `## Parallelisation`, the task ledger and contracts C1-C2 live there and bind every task below.

Tasks: V155-1, V155-2 (spec § 1 and the hook half of § Testing).

**Working directory.** Every command below runs from the worktree root
(`.claude/worktrees/2026-10-10-v155-research-ritual-skills/`). Never `cd` in a
Bash call; relative paths assume the root.

**Two shell traps that bite this part** (index Global Constraints):

1. Test code goes into `tests/hooks/test_guardrails.py` with the **Edit/Write
   tools**, never a shell heredoc or `echo`.
2. Once V155-2's rule is in the worktree's `guardrails.py`, a Bash command that
   carries a whole screen run inside one quoted string is denied. Commit
   messages below name the rule (`_rule_screen_rerun`) and never quote a
   command line; keep it that way.

**One addition to the index's Decision 10** (controller decision, recorded in
contracts C1-C2): a real run with a non-default `--results-dir` is denied on
the same terms as a non-default `--ledger`. A fresh results dir hides the
results doc a run that crashed between the doc write and the ledger append left
behind (`publish`, about `screen_idea.py:395-400`), so it dodges the
results-doc-without-row check exactly as a fresh ledger dodges the row check.

# Phase 1: The screen re-run hook rule

### Task V155-1: v154 precondition; hook constants, segment and flag helpers, ledger and results lookups, docstring, drift test

**Model:** sonnet -- stdlib parsing helpers with a prototype-verified test list; no design left, but shlex and argparse-prefix edge cases need care.

**Files:**
- Modify: `.claude/hooks/guardrails.py` (imports; module docstring; new helper block after `_rule_closed_preregistration`)
- Modify: `tests/hooks/test_guardrails.py` (`import pytest`; new tests and the `screen_repo` fixture appended at the end)
- Modify: `docs/superpowers/plans/2026-10-10-v155-research-ritual-skills_0-index.md` (`## Results`: two rows)

**Interfaces:**
- Consumes: nothing from earlier v155 tasks. From v154 (must be merged): nothing in code; the precondition only.
- Produces (contract C1, consumed by V155-2), all in `.claude/hooks/guardrails.py`:
  - constants `_HOOK_REPO_ROOT: str`, `SCREEN_RESULTS_DIR: str`, `SCREEN_LEDGER_PATH: str`, `_SCREEN_SEPARATORS: frozenset[str]`, `_SCREEN_OPTIONS: tuple[str, ...]`, `_SCREEN_VALUE_KEYS: dict[str, str]`
  - `_line_tokens(line: str) -> list[str] | None`
  - `_split_on_separators(tokens: list[str]) -> list[list[str]]`
  - `_command_segments(cmd: str) -> list[list[str]] | None`
  - `_is_screen_token(tok: str) -> bool`
  - `_is_wrapped_screen(tok: str) -> bool`
  - `_resolve_screen_option(name: str) -> str | None`
  - `_screen_option_values(tokens: list[str])` (generator of `(option, value | None)`)
  - `_screen_flags(tokens: list[str]) -> dict | None`, dict shape exactly `{"idea": str | None, "dry_run": bool, "tickers": bool, "ledger": str | None, "results_dir": str | None}`
  - `_same_repo_path(value: str, target: str) -> bool`, `_is_default_ledger(value: str) -> bool`, `_is_default_results_dir(value: str) -> bool`
  - `_json_row(line: str) -> dict | None`, `_screen_ledger_row(idea: str) -> dict | None`, `_screen_results_doc(idea: str) -> str | None`
  - test-side, in `tests/hooks/test_guardrails.py`: fixture `screen_repo(tmp_path, monkeypatch) -> pathlib.Path` (the temp results dir), helper `_ledger_rows(results, *rows)`, constant `_SCREEN = "python scripts/backtest/screen_idea.py"`

**Why the helpers read module globals at call time** (index Decision 4): the
tests swap `_HOOK_REPO_ROOT`, `SCREEN_RESULTS_DIR` and `SCREEN_LEDGER_PATH` with
`monkeypatch.setattr`. A default argument such as `path=SCREEN_LEDGER_PATH`
would bind the real path at import time and silently read the real ledger.
Never write one.

- [ ] **Step 1: Check the v154 precondition**

v155's skills (part 2) are written against v154's strict frontmatter parser and
`doc_section.py`. Run each check from the worktree root:

```bash
ls scripts/dev/skill_frontmatter.py scripts/dev/doc_section.py
```

Expected: both paths printed, no `No such file`.

```bash
grep -n '"result-digest"' tests/hooks/test_skill_shape.py
grep -n '"handoff"' tests/hooks/test_skill_shape.py
```

Expected: each name appears on the `TIER_2 = {...}` literal (it may also
appear in `FORKED` for `result-digest`).

```bash
grep -n "^## Funnel stages\|^## Evidence, registry and ledger" docs/claude/backtest-methodology.md
```

Expected: two lines, one per heading.

**If any check fails, stop and report to the controller.** Do not create the
v154 files here. Otherwise record the result in the index's `## Results`
table: replace `_not yet run_` on the row `v154 precondition (four checks)` with
`pass -- <short HEAD hash>` (from `git rev-parse --short HEAD`).

- [ ] **Step 2: Add `import pytest` to the test module**

With the Edit tool, in `tests/hooks/test_guardrails.py`, replace:

```python
import pathlib
import re

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
```

with:

```python
import pathlib
import re

import pytest

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
```

(If v154 already added `import pytest`, skip this step.)

- [ ] **Step 3: Write the failing tests**

With the Edit tool (never a shell heredoc -- see the part header), append this
block at the very end of `tests/hooks/test_guardrails.py`:

```python


# --- v155: idea-screen helpers (_rule_screen_rerun's building blocks) -------

_SCREEN = "python scripts/backtest/screen_idea.py"


def test_screen_ledger_path_matches_stats_ledger_path():
    """The hook is stdlib-only, so it carries its own copy of the ledger path;
    this pins it to the one screen_idea.py actually defaults to."""
    from swingbot.core.backtesting.instrument import stats
    assert (pathlib.Path(guardrails.SCREEN_LEDGER_PATH).resolve()
            == stats.LEDGER_PATH.resolve())


def test_screen_results_dir_holds_the_ledger():
    assert (pathlib.Path(guardrails.SCREEN_LEDGER_PATH).parent
            == pathlib.Path(guardrails.SCREEN_RESULTS_DIR))


def test_command_segments_split_on_separators_and_newlines():
    segs = guardrails._command_segments("cd x && ls -la; echo a | wc -l\ngit status")
    assert segs == [["cd", "x"], ["ls", "-la"], ["echo", "a"], ["wc", "-l"],
                    ["git", "status"]]


def test_command_segments_join_backslash_continuations():
    segs = guardrails._command_segments(f"{_SCREEN} \\\n  --idea gap_volume \\\n  --dry-run")
    assert segs == [["python", "scripts/backtest/screen_idea.py", "--idea",
                     "gap_volume", "--dry-run"]]


def test_command_segments_keep_a_quoted_string_whole():
    segs = guardrails._command_segments('bash x.sh "cd /opt && python y.py"')
    assert segs == [["bash", "x.sh", "cd /opt && python y.py"]]


def test_an_untokenisable_screen_line_gives_none():
    assert guardrails._command_segments(f"{_SCREEN} --idea 'gap_volume") is None


def test_an_untokenisable_unrelated_line_is_skipped():
    assert guardrails._command_segments("echo 'oops\ngit status") == [["git", "status"]]


def test_screen_tokens_cover_paths_and_module_names():
    for tok in ("scripts/backtest/screen_idea.py", "scripts\\backtest\\screen_idea.py",
                "screen_idea.py", "screen_idea", "scripts.backtest.screen_idea"):
        assert guardrails._is_screen_token(tok), tok
    for tok in ("screen_idea_notes.md", "tests/test_screen_idea_x.py", "screen"):
        assert not guardrails._is_screen_token(tok), tok


def test_a_wrapped_screen_needs_both_the_name_and_the_idea_flag():
    assert guardrails._is_wrapped_screen(
        f"cd /opt/swing-bot && {_SCREEN} --idea gap_volume")
    assert not guardrails._is_wrapped_screen("docs mention screen_idea.py only")
    assert not guardrails._is_wrapped_screen("scripts/backtest/screen_idea.py")


def test_screen_flags_is_none_for_a_segment_without_the_script():
    assert guardrails._screen_flags(["git", "status"]) is None


def test_screen_flags_read_both_idea_spellings():
    space = guardrails._screen_flags(["python", "screen_idea.py", "--idea", "gap_volume"])
    equals = guardrails._screen_flags(["python", "screen_idea.py", "--idea=gap_volume"])
    assert space["idea"] == equals["idea"] == "gap_volume"


def test_screen_flags_read_every_checked_option():
    flags = guardrails._screen_flags(
        ["python", "-m", "scripts.backtest.screen_idea", "--idea", "x",
         "--tickers", "AAPL,MSFT", "--dry-run", "--ledger", "l.jsonl",
         "--results-dir=r"])
    assert flags == {"idea": "x", "dry_run": True, "tickers": True,
                     "ledger": "l.jsonl", "results_dir": "r"}


def test_screen_flags_resolve_unique_abbreviations_like_argparse():
    flags = guardrails._screen_flags(
        ["python", "screen_idea.py", "--id", "x", "--dry", "--led", "l.jsonl",
         "--res=r"])
    assert flags == {"idea": "x", "dry_run": True, "tickers": False,
                     "ledger": "l.jsonl", "results_dir": "r"}


def test_screen_flags_ignore_an_ambiguous_abbreviation():
    flags = guardrails._screen_flags(["python", "screen_idea.py", "--idea", "x", "--d"])
    assert flags["dry_run"] is False


def test_screen_flags_ignore_tokens_before_the_script():
    flags = guardrails._screen_flags(["X=--dry-run", "python", "screen_idea.py",
                                      "--idea", "x"])
    assert flags["dry_run"] is False


def test_an_empty_tickers_value_is_no_tickers():
    flags = guardrails._screen_flags(["python", "screen_idea.py", "--idea", "x",
                                      "--tickers=", "--dry-run"])
    assert flags["tickers"] is False


@pytest.fixture
def screen_repo(tmp_path, monkeypatch):
    """A throwaway repo root holding an empty results dir, with the hook's
    screen constants pointed at it. Never the real ledger."""
    results = tmp_path / "docs" / "superpowers" / "results"
    results.mkdir(parents=True)
    monkeypatch.setattr(guardrails, "_HOOK_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(guardrails, "SCREEN_RESULTS_DIR", str(results))
    monkeypatch.setattr(guardrails, "SCREEN_LEDGER_PATH",
                        str(results / "preregistration-ledger.jsonl"))
    return results


def _ledger_rows(results, *rows):
    (results / "preregistration-ledger.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_default_ledger_matches_relative_and_absolute_spellings(screen_repo):
    assert guardrails._is_default_ledger(
        "docs/superpowers/results/preregistration-ledger.jsonl")
    assert guardrails._is_default_ledger(
        "./docs/superpowers/results/../results/preregistration-ledger.jsonl")
    assert guardrails._is_default_ledger(str(screen_repo / "preregistration-ledger.jsonl"))
    assert not guardrails._is_default_ledger("fresh.jsonl")


def test_default_results_dir_matches_relative_and_absolute_spellings(screen_repo):
    assert guardrails._is_default_results_dir("docs/superpowers/results")
    assert guardrails._is_default_results_dir("docs/superpowers/results/")
    assert guardrails._is_default_results_dir(str(screen_repo))
    assert not guardrails._is_default_results_dir("elsewhere")


def test_ledger_row_matches_the_exact_id_only(screen_repo):
    _ledger_rows(screen_repo,
                 {"id": "screen-gap_volume_v2", "date": "2026-10-01"},
                 {"id": "screen-gap_volume", "date": "2026-10-02"})
    assert guardrails._screen_ledger_row("gap_volume")["date"] == "2026-10-02"
    assert guardrails._screen_ledger_row("gap") is None


def test_ledger_row_skips_malformed_lines(screen_repo):
    (screen_repo / "preregistration-ledger.jsonl").write_text(
        'not json\n[1, 2]\n{"id": "screen-x", "date": "d"}\n', encoding="utf-8")
    assert guardrails._screen_ledger_row("x") == {"id": "screen-x", "date": "d"}


def test_a_missing_ledger_reads_as_no_row(screen_repo):
    assert guardrails._screen_ledger_row("x") is None


def test_results_doc_is_found_whatever_its_date(screen_repo):
    doc = screen_repo / "2026-10-09-screen-turn_of_month.md"
    doc.write_text("# result\n", encoding="utf-8")
    assert guardrails._screen_results_doc("turn_of_month") == str(doc)
    assert guardrails._screen_results_doc("month") is None


def test_a_missing_results_dir_reads_as_no_doc(screen_repo, monkeypatch):
    monkeypatch.setattr(guardrails, "SCREEN_RESULTS_DIR", str(screen_repo / "absent"))
    assert guardrails._screen_results_doc("x") is None
```

Notes for the implementer:

- `_SCREEN`, `screen_repo` and `_ledger_rows` are reused by V155-2's tests.
  Keep the names.
- `test_results_doc_is_found_whatever_its_date` compares with `str(doc)`.
  `glob` returns paths built from `SCREEN_RESULTS_DIR` (here `str(results)`), so
  both sides carry the native separator; do not normalise either side.
- Every test above passed against a prototype of Step 7's code before this
  plan was written (the drift test only from the real repo root).

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py`

Expected: FAIL. The new tests error with
`AttributeError: module 'guardrails' has no attribute 'SCREEN_LEDGER_PATH'`
(or `'_command_segments'`, `'_is_screen_token'`, ...). Every pre-existing test
still passes.

- [ ] **Step 5: Add the imports**

With the Edit tool, in `.claude/hooks/guardrails.py`, replace:

```python
import json
import os
import re
import sys
```

with:

```python
import glob
import json
import os
import re
import shlex
import sys
```

Both are stdlib. Nothing from `swingbot`, nothing third-party (index Global
Constraints: the hook stays stdlib-only, 5 s timeout unchanged).

- [ ] **Step 6: Rewrite the docstring's purity claim**

The docstring says `evaluate()` reads no files. After this task the
idea-screen lookups read the ledger and glob results docs. With the Edit tool,
replace:

```python
Design: evaluate() reads no files and spawns no subprocesses -- os.path.getsize
and os.getcwd() are the only OS calls -- so the whole rule set is unit-tested in
tests/hooks/test_guardrails.py without a live session. Anything unrecognised
returns None -- silent allow. A guardrail that blocks legitimate work costs more
than the habit it prevents.
```

with:

```python
Design: evaluate() spawns no subprocesses. Its only file reads are the
idea-screen lookups (_screen_ledger_row reads the pre-registration ledger,
_screen_results_doc globs the results docs), and both go through module-level
constants (SCREEN_LEDGER_PATH, SCREEN_RESULTS_DIR) that tests point at
tmp_path. Otherwise os.path.getsize and os.getcwd() are the only OS calls, so
the whole rule set is unit-tested in tests/hooks/test_guardrails.py without a
live session. Anything unrecognised returns None -- silent allow, and a
missing or unreadable ledger reads as "no row". A guardrail that blocks
legitimate work costs more than the habit it prevents.
```

- [ ] **Step 7: Add the helper block**

Anchor on text (index: anchor on text, not line numbers). Find the end of
`_rule_closed_preregistration`:

```bash
grep -n '"this yourself."' .claude/hooks/guardrails.py
```

Expected: one line, inside `_rule_closed_preregistration`'s `_deny(...)`. With
the Edit tool, replace:

```python
        "say so to the human partner and let them authorise it -- do not clear "
        "this yourself."
    )
```

with the same three lines followed by this block (two blank lines before the
comment, PEP 8 spacing between top-level names):

```python
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
    flags = {"idea": None, "dry_run": False, "tickers": False,
             "ledger": None, "results_dir": None}
    for opt, value in _screen_option_values(tokens[start + 1:]):
        if opt == "--dry-run":
            flags["dry_run"] = True
        elif opt == "--tickers":
            flags["tickers"] = bool(value)
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
```

Why each non-obvious line is there:

- `shlex.shlex(..., punctuation_chars=True)` with `whitespace_split = True`
  cuts `a&&b` into `a`, `&&`, `b` while keeping a quoted string one token
  (Python 3.8+ behaviour). Quotes are stripped in posix mode, so
  `"--idea=x"` reads as `--idea=x`.
- `_split_on_separators` leaves out `>` and `<` on purpose: a redirect's target
  belongs to the same command, and the flag reader ignores it anyway.
- `_resolve_screen_option` mirrors `screen_idea.py`'s parser, which keeps
  argparse's default `allow_abbrev=True` (index Decision 6). `--d` matches
  both `--date` and `--dry-run`, so it resolves to `None`; argparse rejects it.
- `_screen_option_values` does not take a value that starts with `-`: argparse
  would treat it as the next option.
- `bool(value)` for `--tickers`: `--tickers=` is an empty comma list, and the
  script treats an empty `args.tickers` as "no tickers", that is, the full
  universe.
- `_same_repo_path` resolves against `_HOOK_REPO_ROOT`, never the session cwd
  (index Decision 5). An absolute `value` survives `os.path.join` unchanged.
- `glob.escape` on the directory too, so a temp path with `[` in it never turns
  into a character class.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py`

Expected: PASS, `0 failed`, `0 xfailed`. If
`test_screen_ledger_path_matches_stats_ledger_path` fails, the hook's
`_HOOK_REPO_ROOT` is wrong (three `dirname` calls above
`.claude/hooks/guardrails.py`); fix the constant, never the test.

- [ ] **Step 9: Check complexity**

Run: `python -m radon cc -s -n C .claude/hooks/guardrails.py`

Expected: only `_rule_recursive_grep_from_root - C (11)` is listed (the
pre-existing maximum). None of the new helpers is rated C; the largest,
`_screen_option_values`, is B (9).

- [ ] **Step 10: Record the drift test result**

In the index's `## Results` table, replace `_not yet run_` on the row
`Drift test SCREEN_LEDGER_PATH == stats.LEDGER_PATH` with
`pass -- test_screen_ledger_path_matches_stats_ledger_path`.

- [ ] **Step 11: Commit**

V155-1 adds no rule, so `AGENTS.md` and `docs/claude/skills-tools.md` do not
change yet (`_rule_codex_mirror_reminder` will remind you; V155-2 carries the
mirror text with the rule itself).

```bash
git add .claude/hooks/guardrails.py tests/hooks/test_guardrails.py docs/superpowers/plans/2026-10-10-v155-research-ritual-skills_0-index.md
git commit -m "feat(hooks): idea-screen command helpers for the v155 re-run rule (V155-1)

Segment splitting with shlex, argparse-style flag reading, default-path
checks and the ledger and results-doc lookups, behind module constants
tests point at tmp_path. Drift test pins the hook's ledger path to
stats.LEDGER_PATH. Docstring no longer claims evaluate() reads no files.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: one commit, three files changed.

### Task V155-2: `_rule_screen_rerun`, registered in `_RULES["Bash"]`; hook-rule docs

**Model:** sonnet -- one rule over V155-1's tested helpers with a prototype-verified test list; the deny texts are a cross-part contract (C2) and must be copied exactly.

**Files:**
- Modify: `.claude/hooks/guardrails.py` (new rule block after `_screen_results_doc`; `_RULES["Bash"]`)
- Modify: `tests/hooks/test_guardrails.py` (new tests appended after V155-1's block)
- Modify: `docs/claude/skills-tools.md` (the v96 hook-rules paragraph; the `Repo tooling` paragraph's deny list)
- Modify: `AGENTS.md` (the hook sentence, "Both agents enforce these habits with one hook")
- Modify: `docs/superpowers/plans/2026-10-10-v155-research-ritual-skills_0-index.md` (`## Results`: the radon row)

**Interfaces:**
- Consumes (contract C1, created by V155-1, all in `.claude/hooks/guardrails.py`): `_HOOK_REPO_ROOT`, `_command_segments(cmd) -> list[list[str]] | None`, `_is_wrapped_screen(tok) -> bool`, `_screen_flags(tokens) -> dict | None` (keys `idea`, `dry_run`, `tickers`, `ledger`, `results_dir`), `_is_default_ledger(value) -> bool`, `_is_default_results_dir(value) -> bool`, `_screen_ledger_row(idea) -> dict | None`, `_screen_results_doc(idea) -> str | None`, and the existing `_deny(reason) -> dict`. Test-side: fixture `screen_repo`, helper `_ledger_rows(results, *rows)`, constant `_SCREEN`, and the existing `_bash(cmd)`.
- Produces (contract C2, consumed by V155-3's `/screen` Step 6 and its Step 1 check):
  - `_rule_screen_rerun(ti: dict) -> dict | None`, registered in `_RULES["Bash"]` immediately after `_rule_closed_preregistration`
  - `_screen_deny_reason(flags: dict) -> str | None`
  - helpers `_SCREEN_DENY_TAIL: str`, `_screen_text(body: str) -> str`, `_repo_relative(path: str) -> str`, `_screen_record_reason(idea: str) -> str | None`, `_has_wrapped_screen(segments: list[list[str]]) -> bool`
  - the deny texts. Every one starts `screen_idea: ` and ends ` -- one shot per idea; see docs/claude/backtest-methodology.md "Funnel stages".`, and carries one fragment: `inside a quoted wrapper`, `could not tokenise`, `--dry-run without --tickers`, `--ledger other than the default`, `--results-dir other than the default`, `screen-<idea> is already in the ledger (<date>, <verdict>, <record>)`, or `results doc <repo-relative path> exists with no ledger row`.

**What the rule decides** (spec § 1; index Decisions 7-10, plus the
`--results-dir` addition recorded in the part header):

| Command | Verdict | Fragment |
|---|---|---|
| no `screen_idea` in the command, or no `--idea` in the screen segment (`--help`, `git grep`, `cat`) | allow | -- |
| a line that mentions `screen_idea` and cannot be tokenised | deny | `could not tokenise` |
| a token that holds both `screen_idea` and `--idea` but is not the script (ssh wrapper, `pwsh -Command`, quoted commit message) | deny | `inside a quoted wrapper` |
| `--dry-run` without a non-empty `--tickers` | deny | `--dry-run without --tickers` |
| `--dry-run` with `--tickers` | allow, even for a screened idea | -- |
| real run, `--ledger` not the default | deny | `--ledger other than the default` |
| real run, `--results-dir` not the default | deny | `--results-dir other than the default` |
| real run, exact ledger row `screen-<idea>` | deny | `screen-<idea> is already in the ledger (...)` |
| real run, `*-screen-<idea>.md` and no row | deny | `results doc ... exists with no ledger row` |
| real run, none of the above | allow | -- |

The untokenisable check runs before the wrapped check because the wrapped check
needs tokens (index contract C2 records this order). The first deny across
segments wins.

- [ ] **Step 1: Write the failing tests**

With the Edit tool (never a shell heredoc -- see the part header), append this
block at the very end of `tests/hooks/test_guardrails.py`, after V155-1's last
test `test_a_missing_results_dir_reads_as_no_doc`:

```python


# --- v155: _rule_screen_rerun (the idea screen's one-shot rule) -------------

_SCREEN_TAIL = (' -- one shot per idea; see docs/claude/backtest-methodology.md '
                '"Funnel stages".')


def _screen_denial(cmd):
    """The deny reason for `cmd`; fails the test when it is not a deny."""
    out = _bash(cmd)
    assert out is not None, cmd
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny", cmd
    reason = hso["permissionDecisionReason"]
    assert reason.startswith("screen_idea: ") and reason.endswith(_SCREEN_TAIL)
    return reason


def _screened(results, idea="gap_volume"):
    """`idea` with a ledger row and its results doc, as a finished screen."""
    record = f"docs/superpowers/results/2026-10-09-screen-{idea}.md"
    _ledger_rows(results, {"id": f"screen-{idea}", "date": "2026-10-09",
                           "verdict": "SCREEN-FAIL", "record": record})
    (results / f"2026-10-09-screen-{idea}.md").write_text("# r\n", encoding="utf-8")


def test_screen_rerun_rule_runs_right_after_the_closed_preregistration_rule():
    bash_rules = guardrails._RULES["Bash"]
    i = bash_rules.index(guardrails._rule_closed_preregistration)
    assert bash_rules[i + 1] is guardrails._rule_screen_rerun


def test_a_first_real_run_is_allowed(screen_repo):
    assert _bash(f"{_SCREEN} --idea gap_volume") is None


def test_a_rerun_of_a_screened_idea_is_denied_with_its_ledger_row(screen_repo):
    _screened(screen_repo)
    reason = _screen_denial(f"{_SCREEN} --idea gap_volume")
    assert ("screen-gap_volume is already in the ledger (2026-10-09, SCREEN-FAIL, "
            "docs/superpowers/results/2026-10-09-screen-gap_volume.md)") in reason


def test_both_idea_spellings_are_denied(screen_repo):
    _screened(screen_repo)
    _screen_denial(f"{_SCREEN} --idea=gap_volume")
    _screen_denial(f"{_SCREEN} --idea gap_volume")


def test_only_the_exact_ledger_id_denies(screen_repo):
    _ledger_rows(screen_repo, {"id": "screen-gap_volume_v2", "date": "d",
                               "verdict": "v", "record": "r"})
    assert _bash(f"{_SCREEN} --idea gap_volume") is None
    assert _bash(f"{_SCREEN} --idea gap") is None


def test_a_results_doc_with_no_ledger_row_is_denied(screen_repo):
    (screen_repo / "2026-10-08-screen-turn_of_month.md").write_text(
        "# r\n", encoding="utf-8")
    reason = _screen_denial(f"{_SCREEN} --idea turn_of_month")
    assert ("results doc docs/superpowers/results/2026-10-08-screen-turn_of_month.md "
            "exists with no ledger row") in reason


def test_a_full_universe_dry_run_is_denied(screen_repo):
    reason = _screen_denial(f"{_SCREEN} --idea gap_volume --dry-run")
    assert "--dry-run without --tickers" in reason


def test_an_abbreviated_full_universe_dry_run_is_denied(screen_repo):
    assert "--dry-run without --tickers" in _screen_denial(
        f"{_SCREEN} --idea gap_volume --dry")


def test_a_tickers_dry_run_is_allowed_even_for_a_screened_idea(screen_repo):
    _screened(screen_repo)
    assert _bash(f"{_SCREEN} --idea gap_volume --tickers AAPL,MSFT --dry-run") is None


def test_a_non_default_ledger_is_denied(screen_repo):
    reason = _screen_denial(f"{_SCREEN} --idea gap_volume --ledger fresh.jsonl")
    assert "--ledger other than the default (fresh.jsonl)" in reason


def test_a_non_existent_ledger_is_denied(screen_repo):
    reason = _screen_denial(
        f"{_SCREEN} --idea gap_volume --led=/nowhere/absent.jsonl")
    assert "--ledger other than the default" in reason


def test_the_default_ledger_spelled_out_is_allowed(screen_repo):
    assert _bash(f"{_SCREEN} --idea gap_volume --ledger "
                 "docs/superpowers/results/preregistration-ledger.jsonl") is None


def test_a_non_default_results_dir_is_denied(screen_repo):
    reason = _screen_denial(f"{_SCREEN} --idea gap_volume --results-dir scratch")
    assert "--results-dir other than the default (scratch)" in reason


def test_a_non_default_results_dir_hides_no_doc_from_the_rule(screen_repo):
    (screen_repo / "2026-10-08-screen-gap_volume.md").write_text(
        "# r\n", encoding="utf-8")
    reason = _screen_denial(f"{_SCREEN} --idea gap_volume --res=elsewhere")
    assert "--results-dir other than the default (elsewhere)" in reason


def test_the_default_results_dir_spelled_out_is_allowed(screen_repo):
    assert _bash(f"{_SCREEN} --idea gap_volume "
                 "--results-dir docs/superpowers/results") is None


def test_a_chained_command_reads_the_screen_segment(screen_repo):
    _screened(screen_repo)
    _screen_denial(f"cd scripts && cd .. && {_SCREEN} --idea gap_volume")
    assert _bash("echo --dry-run && "
                 f"{_SCREEN} --idea fresh_idea --tickers AAPL --dry-run") is None


def test_the_first_denying_segment_wins(screen_repo):
    _screened(screen_repo)
    reason = _screen_denial(
        f"{_SCREEN} --idea fresh_idea; {_SCREEN} --idea gap_volume --dry-run")
    assert "--dry-run without --tickers" in reason


def test_a_backslash_continued_command_is_read_whole(screen_repo):
    reason = _screen_denial(f"{_SCREEN} \\\n  --idea gap_volume \\\n  --dry-run")
    assert "--dry-run without --tickers" in reason


def test_the_module_form_is_read(screen_repo):
    _screened(screen_repo)
    _screen_denial("python -m scripts.backtest.screen_idea --idea gap_volume")


def test_a_quoted_ssh_wrapper_is_denied(screen_repo):
    reason = _screen_denial(
        'bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && '
        f'{_SCREEN} --idea gap_volume"')
    assert "inside a quoted wrapper" in reason


def test_a_pwsh_wrapper_is_denied(screen_repo):
    reason = _screen_denial(f"pwsh -Command '{_SCREEN} --idea gap_volume'")
    assert "inside a quoted wrapper" in reason


def test_an_untokenisable_screen_line_is_denied(screen_repo):
    reason = _screen_denial(f"{_SCREEN} --idea 'gap_volume")
    assert "could not tokenise" in reason


def test_mentions_of_the_script_without_a_run_are_allowed(screen_repo):
    _screened(screen_repo)
    for cmd in ("git grep -n screen_idea", 'git grep -n "screen_idea.py"',
                "cat scripts/backtest/screen_idea.py",
                f"{_SCREEN} --help"):
        assert _bash(cmd) is None, cmd


def test_screen_rerun_rule_fails_open_on_a_missing_command():
    assert guardrails._rule_screen_rerun({}) is None
    assert guardrails._rule_screen_rerun({"command": 7}) is None
```

Notes for the implementer:

- Every test that can reach the ledger or the results dir takes `screen_repo`,
  so none of them reads the real `docs/superpowers/results/`. Keep it that way:
  a new test without the fixture would see the real `screen-gap_volume` row.
- `test_a_non_default_results_dir_hides_no_doc_from_the_rule` is the
  controller's `--results-dir` case: a fresh results dir would hide the doc a
  crashed run left behind, so it is denied on the same terms as a fresh ledger,
  before the record lookups run.
- `--led=` and `--res=` are argparse abbreviations (index Decision 6), read by
  V155-1's `_resolve_screen_option`.
- `/nowhere/absent.jsonl` is not the default ledger on either platform: on
  Windows `os.path.join` keeps the temp drive and gives `<drive>:/nowhere/...`.
- Every test above passed against a prototype of Step 3's code on top of
  V155-1's helper block before this plan was written.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py`

Expected: FAIL. The deny tests fail with `AssertionError` (no rule reads a
screen command yet, so the hook returns `None`), and the two tests that name
the rule fail with
`AttributeError: module 'guardrails' has no attribute '_rule_screen_rerun'`.
The allow tests (`test_a_first_real_run_is_allowed`,
`test_only_the_exact_ledger_id_denies`, ...) already pass, which is expected.
Every V155-1 test and every pre-existing test still passes.

- [ ] **Step 3: Add the rule block**

Anchor on text. Find the end of V155-1's helper block:

```bash
grep -n "return hits\[0\] if hits else None" .claude/hooks/guardrails.py
```

Expected: one line, the last line of `_screen_results_doc`. With the Edit tool,
replace:

```python
    hits = sorted(glob.glob(pattern))
    return hits[0] if hits else None
```

with the same two lines followed by this block (two blank lines between
top-level names):

```python
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
```

Why each non-obvious line is there:

- `"screen_idea" not in cmd` returns first, so every other Bash command costs
  one substring test and never reaches `shlex`, the ledger or the glob.
- The untokenisable and wrapped checks fail closed on purpose (index Global
  Constraints: the two written exceptions to fail-open). Everything else fails
  open: `evaluate()` already catches any exception a rule raises, a missing
  ledger reads as no row, and a missing results dir as no doc.
- `flags["idea"] is None` skips the segment: `--help`, `git grep -n
  screen_idea` and `cat scripts/backtest/screen_idea.py` all hold a screen
  token but run nothing (index Decision 9).
- `_screen_deny_reason` decides a dry run on `--tickers` alone and returns
  before any path check. `screen_idea.py` writes nothing on `--dry-run`, so a
  smoke test against a scratch ledger spends no shot.
- The `--results-dir` check sits beside the `--ledger` check and before the
  record lookups: a fresh results dir would hide a results doc that a run
  crashing between the doc write and the ledger append (`publish`, about
  `screen_idea.py:395-400`) left behind.
- `_repo_relative` makes the doc path read the way the ledger's `record` field
  does (`docs/superpowers/results/...`, `/` separators). `os.path.relpath`
  raises `ValueError` across Windows drives; the raw path is the fallback,
  never an exception that would fail the rule open.
- `row.get(...)`: a malformed row that lacks a field still denies, and prints
  `None` for what is missing.

- [ ] **Step 4: Register the rule**

With the Edit tool, in `_RULES`, replace:

```python
    "Bash": [_rule_protected_branch_delete, _rule_closed_preregistration,
             _rule_recursive_grep_from_root, _rule_bare_pytest, _rule_cat_big_doc],
```

with:

```python
    "Bash": [_rule_protected_branch_delete, _rule_closed_preregistration,
             _rule_screen_rerun, _rule_recursive_grep_from_root,
             _rule_bare_pytest, _rule_cat_big_doc],
```

If v154 or another plan changed that list first, keep its entries and insert
`_rule_screen_rerun` directly after `_rule_closed_preregistration`, which is
what `test_screen_rerun_rule_runs_right_after_the_closed_preregistration_rule`
checks.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py`

Expected: PASS, `0 failed`, `0 xfailed`. If
`test_mentions_of_the_script_without_a_run_are_allowed` fails, the `idea is
None` skip is missing; if a `screen_repo` test sees a real ledger row, a helper
bound a path as a default argument (V155-1, index Decision 4).

- [ ] **Step 6: Check complexity**

Run: `python -m radon cc -s -n B .claude/hooks/guardrails.py`

Expected, among the listed functions: `_rule_recursive_grep_from_root - C (11)`
(unchanged, still the file's maximum), `_screen_option_values - B (9)`,
`_rule_screen_rerun - B (9)`, `_screen_flags - B (8)`,
`_screen_deny_reason - B (7)`. Nothing is rated C (15) or above.

Record it: in the index's `## Results` table, replace `_not yet run_` on the
row `radon cc -s -n C .claude/hooks/guardrails.py` with
`pass -- max C (11) _rule_recursive_grep_from_root; _rule_screen_rerun B (9)`
(use the figures radon actually printed).

- [ ] **Step 7: Name the rule in `docs/claude/skills-tools.md`**

Anchor on text (v154 edits this file first, so line numbers moved):

```bash
grep -n "heading)\.$\|closed-pre-registration knobs and malformed" docs/claude/skills-tools.md
```

Expected: two lines, the end of the v96 hook-rules paragraph and the
`Repo tooling` paragraph's deny list.

With the Edit tool, replace:

```markdown
`docs/superpowers/{specs,plans}/` whose filename isn't
`YYYY-MM-DD-vN-<name>.md`, or whose content has a two-hash `## Phase`
heading).
```

with:

```markdown
`docs/superpowers/{specs,plans}/` whose filename isn't
`YYYY-MM-DD-vN-<name>.md`, or whose content has a two-hash `## Phase`
heading). v155 added a fourth deny rule, `_rule_screen_rerun` (denies a
re-run or a full-universe dry run of a screened idea, a real run against a
non-default `--ledger` or `--results-dir`, and a screen run inside a quoted
wrapper; it reads flags only from the shell segment that runs
`screen_idea.py`).
```

Then replace:

```markdown
protected-branch deletion, closed-pre-registration knobs and malformed
spec/plan writes — and warns on bare `pytest`/`cat` of the big docs, unit-
```

with:

```markdown
protected-branch deletion, closed-pre-registration knobs, re-runs of a
screened idea and malformed spec/plan writes — and warns on bare
`pytest`/`cat` of the big docs, unit-
```

- [ ] **Step 8: Name the rule in `AGENTS.md`**

```bash
grep -n "knobs and malformed spec/plan names" AGENTS.md
```

Expected: one line, inside "Both agents enforce these habits with one hook".
With the Edit tool, replace:

```markdown
from the main tree, protected-branch deletion, closed-pre-registration backtest
knobs and malformed spec/plan names, and warns on bare `pytest`, `cat` of the
```

with:

```markdown
from the main tree, protected-branch deletion, closed-pre-registration backtest
knobs, a re-run or full-universe dry run of a screened idea
(`_rule_screen_rerun`) and malformed spec/plan names, and warns on bare
`pytest`, `cat` of the
```

The sentence that follows ("Codex runs a new or changed hook only after it is
trusted in `/hooks`") already covers the new rule; do not change it. The edit
fires `_rule_codex_mirror_reminder` as a warning: this step is the mirror it
asks for.

- [ ] **Step 9: Run the mirror and hook tests**

Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`

Expected: PASS, `0 failed`, `0 xfailed` (no skill changed, so the mirror is
still current).

Run: `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py`

Expected: PASS, `0 failed`, `0 xfailed` (the doc edits did not break a test
that reads `docs/claude/`).

- [ ] **Step 10: Commit**

The message names the rule and never quotes a screen command line: the rule
just committed treats a quoted line holding the script and its idea flag as a
wrapped run (index Global Constraints).

```bash
git add .claude/hooks/guardrails.py tests/hooks/test_guardrails.py docs/claude/skills-tools.md AGENTS.md docs/superpowers/plans/2026-10-10-v155-research-ritual-skills_0-index.md
git commit -m "feat(hooks): _rule_screen_rerun denies a re-run of a screened idea (V155-2)

Reads flags only from the shell segment that runs the idea screen. Denies
a real run of an idea with an exact ledger row or a results doc, a
full-universe dry run, a non-default ledger or results dir, a quoted
wrapper and an untokenisable line. Registered right after
_rule_closed_preregistration; named in skills-tools.md and AGENTS.md.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: one commit, five files changed. `git status --short` shows none of
them still modified.
